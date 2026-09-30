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

// 주인(관리자 비밀번호로 들어온 기기)의 방문은 모든 숫자에서 뺀다. 한 군데라도
// 빠뜨리면 그 지표만 부풀어 오른다 — 그래서 조각을 하나로 두고 전부 같은 것을 쓴다.
const 주인빼기 = 'AND visitor NOT IN (SELECT o.visitor FROM owner o)';

// 유입만 세션의 첫 줄로 좁힌다(설계 §6.3). MIN(id) 옆의 열은 **최솟값이 나온 그
// 행의 값**이다 — SQLite 가 min()/max() 단일 집계에 보장하는 동작이고 D1 은
// SQLite 다. 다른 DB 로 옮기면 깨지는 자리라 옮길 일이 생기면 여기부터 본다.
//
// 주인빼기는 이 하위질의 **안**에 붙인다 — 바깥(유입종류·유입호스트 쪽)에 붙이면
// 이미 GROUP BY 로 접힌 뒤라 visitor 열이 없어 질의 자체가 깨진다.
const 세션첫줄 = `SELECT session, ref, ref_kind, MIN(id) FROM hit
  WHERE day BETWEEN ?1 AND ?2 ${주인빼기} GROUP BY session`;

export function 질의목록(창) {
  const p = [창.시작, 창.끝];
  const 목록 = [
    { 키: '요약', sql: `SELECT COUNT(DISTINCT visitor) 방문자, COUNT(DISTINCT session) 세션,
        COUNT(*) 조회 FROM hit WHERE day BETWEEN ?1 AND ?2 ${주인빼기}`, params: p },
    // 방문 한 번 = 세션 하나(탭의 sessionStorage 가 사는 동안). 신규는 첫 방문이
    // 기간 안인 사람, 재방문은 기간 안에 **첫 방문이 아닌 세션**이 있는 사람이다 —
    // 같은 날 다시 와도 재방문이다. 기간 안 세션 수가 "첫 방문이 기간 안이면 1, 아니면 0"
    // 보다 많으면 그런 세션이 있다. 그래서 둘은 겹친다(이번 주 처음 와서 또 온 사람).
    // 예전엔 재방문을 "첫 방문일이 기간 시작 전" 으로 셌다 — 기간 안에서 처음 오고
    // 다시 온 사람이 신규로만 잡혀, 수집 첫 30일과 전 기간 창에서 재방문이 늘 0 이었다.
    // 주인빼기는 안쪽 하위질의에 붙인다 — 바깥 JOIN 은 visitor 표 전체를 본다.
    { 키: '신규', sql: `SELECT
        SUM(CASE WHEN v.first_day >= ?1 THEN 1 ELSE 0 END) 신규,
        SUM(CASE WHEN h.세션수 > (CASE WHEN v.first_day >= ?1 THEN 1 ELSE 0 END)
          THEN 1 ELSE 0 END) 재방문
      FROM (SELECT visitor, COUNT(DISTINCT session) 세션수 FROM hit
            WHERE day BETWEEN ?1 AND ?2 ${주인빼기} GROUP BY visitor) h
      JOIN visitor v ON v.id = h.visitor`, params: p },
    // 마지막 `domain` 은 동점을 깨는 기준이다. 없으면 방문자·조회가 같은 도메인의
    // 순서가 미정이라 테스트가 운에 기댄다(실제로 실행해 보니 우연히 맞았다).
    { 키: '도메인', sql: `SELECT domain 도메인, COUNT(DISTINCT visitor) 방문자,
        COUNT(DISTINCT session) 세션, COUNT(*) 조회 FROM hit WHERE day BETWEEN ?1 AND ?2 ${주인빼기}
      GROUP BY domain ORDER BY 방문자 DESC, 조회 DESC, domain`, params: p },
    // 도메인별 재방문: 그 도메인에서 **그 사람의 첫 방문이 아닌 세션**이 있는 방문자.
    // 사이트 첫 방문에 본 도메인은 그 세션으론 안 세고, 다시 와서 본 도메인만 센다 —
    // "어느 도메인이 사람을 다시 부르나" 에 답하려는 숫자다. 첫 세션은 첫 방문일의
    // 가장 이른 줄로 찾는다(hit_day 인덱스를 탄다).
    { 키: '도메인재방문', sql: `SELECT h.domain 도메인, COUNT(DISTINCT h.visitor) 재방문
      FROM hit h JOIN visitor v ON v.id = h.visitor
      WHERE h.day BETWEEN ?1 AND ?2
        AND h.visitor NOT IN (SELECT o.visitor FROM owner o)
        AND h.session <> (SELECT f.session FROM hit f
          WHERE f.day = v.first_day AND f.visitor = v.id ORDER BY f.id LIMIT 1)
      GROUP BY h.domain`, params: p },
    { 키: '일별', sql: `SELECT day 날짜, domain 도메인, COUNT(DISTINCT visitor) 방문자,
        COUNT(*) 조회 FROM hit WHERE day BETWEEN ?1 AND ?2 ${주인빼기}
      GROUP BY day, domain ORDER BY day`, params: p },
    // 그날의 정확한 순방문자. 위 `일별` 은 도메인별로 쪼개져 있어 거기서 사람 수를
    // 합치면 두 도메인을 본 사람이 두 번 세어진다 — 날짜로만 묶어 따로 묻는다.
    { 키: '일별방문자', sql: `SELECT day 날짜, COUNT(DISTINCT visitor) 방문자
      FROM hit WHERE day BETWEEN ?1 AND ?2 ${주인빼기} GROUP BY day`, params: p },
    { 키: '화면', sql: `SELECT domain 도메인, path 경로, COUNT(*) 조회,
        COUNT(DISTINCT visitor) 방문자 FROM hit WHERE day BETWEEN ?1 AND ?2 ${주인빼기}
      GROUP BY domain, path ORDER BY 조회 DESC, 도메인, 경로 LIMIT 20`, params: p },
    { 키: '유입종류', sql: `SELECT ref_kind 종류, COUNT(*) 세션 FROM (${세션첫줄})
      GROUP BY ref_kind ORDER BY 세션 DESC`, params: p },
    { 키: '유입호스트', sql: `SELECT ref 호스트, COUNT(*) 세션 FROM (${세션첫줄})
      WHERE ref IS NOT NULL GROUP BY ref ORDER BY 세션 DESC LIMIT 10`, params: p },
    { 키: '기기', sql: `SELECT device 값, COUNT(DISTINCT visitor) 방문자
      FROM hit WHERE day BETWEEN ?1 AND ?2 ${주인빼기} GROUP BY device ORDER BY 방문자 DESC`, params: p },
    { 키: '표시모드', sql: `SELECT mode 값, COUNT(DISTINCT visitor) 방문자
      FROM hit WHERE day BETWEEN ?1 AND ?2 ${주인빼기} GROUP BY mode ORDER BY 방문자 DESC`, params: p },
    { 키: '국가', sql: `SELECT country 값, COUNT(DISTINCT visitor) 방문자
      FROM hit WHERE day BETWEEN ?1 AND ?2 AND country IS NOT NULL ${주인빼기}
      GROUP BY country ORDER BY 방문자 DESC LIMIT 10`, params: p },
  ];
  if (창.직전시작) {
    목록.push({ 키: '직전', sql: `SELECT COUNT(DISTINCT visitor) 방문자,
        COUNT(DISTINCT session) 세션, COUNT(*) 조회 FROM hit WHERE day BETWEEN ?1 AND ?2 ${주인빼기}`,
      params: [창.직전시작, 창.직전끝] });
    // 전체 증감만으로는 "어느 도메인이 늘었나"에 답을 못 한다(design §1·§7.2) —
    // 그 판단을 받쳐 주는 숫자라 도메인별로도 직전 기간을 물어 둔다.
    목록.push({ 키: '직전도메인', sql: `SELECT domain 도메인,
        COUNT(DISTINCT visitor) 방문자 FROM hit WHERE day BETWEEN ?1 AND ?2 ${주인빼기} GROUP BY domain`,
      params: [창.직전시작, 창.직전끝] });
  }
  return 목록;
}

const 수 = (v) => Number(v ?? 0);

export function 조립(창, r) {
  const 요약 = r.요약?.[0] ?? {};
  const 신규 = r.신규?.[0] ?? {};
  const 직전 = r.직전?.[0] ?? null;

  // 직전 기간이 없으면(전 기간, days=0) 도메인마다 필드 자체를 안 붙인다 —
  // "직전이 없다"와 "직전이 0이다"는 다른 사실이고, 0 으로 채우면 그 둘이
  // 뭉개져 델타()가 거짓으로 "-100%"를 그리게 된다.
  const 직전도메인맵 = r.직전도메인
    ? new Map(r.직전도메인.map((row) => [row.도메인, 수(row.방문자)]))
    : null;
  const 재방문맵 = new Map((r.도메인재방문 ?? []).map((row) => [row.도메인, 수(row.재방문)]));
  const 도메인 = (r.도메인 ?? []).map((d) => {
    const 붙임 = { ...d, 재방문: 재방문맵.get(d.도메인) ?? 0 };
    return 직전도메인맵 ? { ...붙임, 직전방문자: 직전도메인맵.get(d.도메인) ?? 0 } : 붙임;
  });

  // 일별은 (날짜, 도메인) 쌍으로 오므로 날짜로 접는다. 그날 0 인 도메인은 아예
  // 행이 없다 — 화면이 0 으로 채운다. 방문자는 `일별방문자` 의 정확한 값을 붙인다.
  const 일방문자 = new Map((r.일별방문자 ?? []).map((row) => [row.날짜, 수(row.방문자)]));
  const 날짜별 = new Map();
  for (const row of r.일별 ?? []) {
    if (!날짜별.has(row.날짜)) {
      날짜별.set(row.날짜, { 날짜: row.날짜, 방문자: 일방문자.get(row.날짜) ?? 0, 도메인별: {} });
    }
    날짜별.get(row.날짜).도메인별[row.도메인] = 수(row.조회);
  }

  return {
    기간: { 시작: 창.시작, 끝: 창.끝, 일수: 창.일수 },
    요약: {
      방문자: 수(요약.방문자), 세션: 수(요약.세션), 조회: 수(요약.조회),
      신규: 수(신규.신규), 재방문: 수(신규.재방문),
    },
    직전: 직전 ? { 방문자: 수(직전.방문자), 세션: 수(직전.세션), 조회: 수(직전.조회) } : null,
    도메인,
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

// 순수 함수만 둔다. DOM도 네트워크도 모른다 — 화면이 바뀌어도 이 파일은 안 바뀐다.

export function esc(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
  ));
}

// 회차 라벨은 데이터가 들고 있다('26.8월분). 화면이 다시 만들지 않는다 —
// 두 곳에서 만들면 언젠가 다르게 쓴다.
export function roundOf(rounds, release) {
  return rounds.find((r) => r.release === release) || rounds[0] || null;
}

export function dayLabel(iso) {
  if (!iso || iso.length < 10) return '';
  return `${iso.slice(5, 7)}.${iso.slice(8, 10)}`;
}

export function timeLabel(pub) {
  // pub 은 '2026-09-07 17:02' 꼴. 날짜와 시각을 같이 보여야 하루 안의 순서가 보인다.
  if (!pub) return '';
  const d = dayLabel(pub);
  const t = pub.length >= 16 ? pub.slice(11, 16) : '';
  return t ? `${d} ${t}` : d;
}

// 배포일 → '보도 D일차'. 후속 구간이 며칠째인지 화면 여러 곳에서 쓴다.
export function daysSince(release, iso) {
  if (!release || !iso) return null;
  const a = Date.parse(`${release}T00:00:00+09:00`);
  const b = Date.parse(`${iso.slice(0, 10)}T00:00:00+09:00`);
  if (Number.isNaN(a) || Number.isNaN(b)) return null;
  return Math.round((b - a) / 86400000);
}

/** 축 안에서만 비교한다 — 축마다 눈금이 다르므로 최댓값도 축마다 따로 잡는다. */
export function scale(rows) {
  const max = rows.reduce((m, r) => Math.max(m, r.n), 0);
  return rows.map((r) => ({ ...r, pct: max > 0 ? Math.round((r.n / max) * 100) : 0 }));
}

/** 화면이 「인용 기사」라고 부르는 것.
 *
 * 수치를 전했고(`cites`) **그 수치가 기사의 본론인**(`focus === '주제'`) 것만이다.
 * 「'싼 게 비지떡' 청년 주거 엇박」처럼 주거·주식·수기 기사가 도입부에 통계를
 * 끌어다 쓴 것은 인용은 맞지만 이 보도자료의 후속 보도가 아니다 — 그것까지
 * 세면 「이 회차가 어디까지 번졌나」가 부풀어 보인다.
 *
 * 판정에 무게가 아직 없는 옛 데이터에서는 `cites` 만으로 본다(빈 화면보다 낫다).
 */
export function isCited(a) {
  if (!a.cites) return false;
  return a.focus === undefined || a.focus === '' || a.focus === '주제';
}

/** 기사 목록 필터. kw 가 있으면 제목에 그 말이 든 기사만. */
export function filterArticles(arts, { onlyCited = true, kw = null } = {}) {
  return arts.filter((a) => {
    if (onlyCited && !isCited(a)) return false;
    if (kw && !a.title.includes(kw)) return false;
    return true;
  });
}

/** 회차별 청년 보도 비중 — 회차 화면의 비교 축. */
export function youthShare(round) {
  const cited = round.regular.cited;
  if (!cited) return 0;
  const row = round.coverage.age.find((x) => x.name === '29세이하·청년');
  return row ? Math.round((row.n / cited) * 100) : 0;
}

/** 인용률 — 수집한 것 중 이 회차 보도자료를 실제로 전한 비율. */
export function citeRate(round) {
  const kept = round.regular.kept;
  return kept ? Math.round((round.regular.cited / kept) * 100) : 0;
}

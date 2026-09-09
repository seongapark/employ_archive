// 목록 가공. DOM 도 네트워크도 모른다 — 화면이 바뀌어도 이 파일은 안 바뀐다.
// (JSON 로드는 app.js 가 core/shell.js 의 loadJson 으로 한다. 여기서 부르면
//  테스트가 조립 전 트리에서 ../core/ 를 못 찾는다.)

export function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
  ));
}

// 화면은 date_precision 보다 자세히 적지 않는다. 없는 정밀도를 지어내면
// "2025년 12월 31일 발간"이라고 단정하게 되는데, 그건 데이터에 없는 말이다.
export function dateLabel(published, precision) {
  const [y, m, d] = String(published || '').split('-');
  if (!y) return '';
  if (precision === 'year') return `${y}년`;
  if (precision === 'month') return `${y}.${m}`;
  return `${y}.${m}.${d}`;
}

export function monthKey(published) {
  return String(published || '').slice(0, 7);
}

export function monthLabel(key) {
  const [y, m] = String(key || '').split('-');
  return y ? `${y}년 ${Number(m)}월` : '';
}

export function filterReports(reports, { orgs = [], years = [] } = {}) {
  return (reports || []).filter((r) => {
    if (orgs.length && !orgs.includes(r.org)) return false;
    if (years.length && !years.includes(Number(String(r.published).slice(0, 4)))) return false;
    return true;
  });
}

export function yearsOf(reports) {
  const set = new Set((reports || []).map((r) => Number(String(r.published).slice(0, 4))));
  return [...set].filter(Boolean).sort((a, b) => b - a);
}

// 같은 달·같은 기관·같은 시리즈가 min 건을 넘으면 한 줄로 접는다.
// 연구보고서류는 12~2월에 몰려서, 접지 않으면 그 달의 타임라인이 한 기관 한
// 시리즈로 뒤덮이고 다른 기관 발간물이 화면 밖으로 밀린다. 브리프류는 낱개로
// 나오고 제목이 곧 내용이라 접으면 정보가 사라지므로 접지 않는다.
export function groupTimeline(reports, boards, { min = 5, expanded = new Set() } = {}) {
  const collapsible = new Set(
    (boards || []).filter((b) => b.collapse).map((b) => b.id)
  );
  const byMonth = new Map();
  for (const r of reports || []) {
    const key = monthKey(r.published);
    if (!byMonth.has(key)) byMonth.set(key, []);
    byMonth.get(key).push(r);
  }
  const groups = [];
  for (const [month, rows] of [...byMonth.entries()].sort((a, b) => (a[0] < b[0] ? 1 : -1))) {
    const buckets = new Map();
    for (const r of rows) {
      const key = `${r.org}|${r.series}`;
      if (!buckets.has(key)) buckets.set(key, []);
      buckets.get(key).push(r);
    }
    const out = [];
    for (const r of rows) {
      const key = `${r.org}|${r.series}`;
      const bucket = buckets.get(key);
      const foldable = collapsible.has(r.board) && bucket.length > min;
      if (!foldable) {
        out.push({ kind: 'report', report: r });
        continue;
      }
      if (bucket[0] !== r) continue;          // 묶음당 한 줄만 낸다
      const id = `${month}|${key}`;
      if (expanded.has(id)) {
        out.push({ kind: 'collapsed', id, label: labelOf(r), count: bucket.length, open: true });
        for (const item of bucket) out.push({ kind: 'report', report: item, inGroup: true });
      } else {
        out.push({ kind: 'collapsed', id, label: labelOf(r), count: bucket.length, open: false });
      }
    }
    groups.push({ month, rows: out });
  }
  return groups;
}

// 기관 코드가 kli·keis·kdi·kiet 라 대문자로 올리면 그대로 통용 약칭이 된다.
// 그래서 이 함수가 orgs.json 을 받지 않아도 된다.
export function labelOf(report) {
  return `${String(report.org || '').toUpperCase()} ${report.series || ''}`.trim();
}

// 추천 — 전량 아카이브의 입구다.
// 1,500건이 넘는(앞으로 2천 건대) 타임라인에서 읽을 걸 찾는 건 사람 일이 아니다.
// 여기서 관심축별로 묶어 내놓고, 왜 골랐는지를 같이 적는다. 이유가 없으면
// 추천을 믿을 근거가 없다.
//
// recommendations.json 은 판정을 실제로 돌려야 생긴다 — 그 전까지는
// ctx.picks 가 undefined 이거나 {} 다. groupByAxis 가 두 경우 모두 빈 배열을
// 돌려주고, render 는 그때 '아직 없다' 를 보인다.
// 축마다 최신 TOP 건만 내놓는다. 849건을 다 펼치면 첫 축 159행 아래에
// 두 번째 축 제목이 묻혀, 어떤 테마로 추천되는지 자체를 볼 수 없다.
// 나머지는 타임라인·검색에서 본다 — 여기는 입구다.
import { esc } from '../data.js';
import { reportRow, empty } from '../ui.js';

export const TOP = 3;

export function groupByAxis(reports, picks) {
  const byAxis = new Map();
  for (const r of reports || []) {
    const p = (picks || {})[r.id];
    if (!p || !p.pick) continue;
    const axis = p.axis || '그 밖';
    if (!byAxis.has(axis)) byAxis.set(axis, []);
    byAxis.get(axis).push({ ...r, why: p.why });
  }
  for (const rows of byAxis.values()) {
    rows.sort((a, b) => (a.published < b.published ? 1 : -1));
  }
  return [...byAxis.entries()]
    .map(([axis, rows]) => ({ axis, rows }))
    .sort((a, b) => b.rows.length - a.rows.length || (a.axis < b.axis ? -1 : 1));
}

export function render(el, ctx) {
  const groups = groupByAxis(ctx.reports, ctx.picks);
  const total = groups.reduce((n, g) => n + g.rows.length, 0);
  if (!total) {
    el.innerHTML = empty('아직 추천할 보고서가 없습니다.');
    return;
  }
  el.innerHTML = `
    <div class="section-title">추천 · ${groups.length}개 테마 · 테마별 최신 ${TOP}건 (전체 ${total}건)</div>
    ${groups.map((g) => {
      const shown = g.rows.slice(0, TOP);
      const rest = g.rows.length - shown.length;
      return `
      <div class="axis">
        <div class="axis__name">${esc(g.axis)} <span class="axis__count">${g.rows.length}</span></div>
        <div class="list">
          ${shown.map((r) => reportRow(r, { why: r.why })).join('')}
        </div>
        ${rest ? `<div class="axis__more">그 밖 ${rest}건 — 타임라인·검색에서 봅니다</div>` : ''}
      </div>`;
    }).join('')}`;
}

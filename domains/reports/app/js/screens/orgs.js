// 기관 — 뭐가 있는지 모를 때 서가를 훑는 화면.
import { esc } from '../data.js';
import { reportRow, orgBadge, empty } from '../ui.js';

export function shelf(reports, orgs) {
  return (orgs || []).map((o) => {
    const rows = (reports || []).filter((r) => r.org === o.code);
    const count = new Map();
    for (const r of rows) count.set(r.series, (count.get(r.series) || 0) + 1);
    return {
      org: o.code,
      name: o.name,
      total: rows.length,
      series: [...count.entries()]
        .map(([series, n]) => ({ series, count: n }))
        .sort((a, b) => b.count - a.count),
    };
  });
}

export function render(el, ctx) {
  const [code, series] = ctx.route.params;
  if (!code) {
    const shelves = shelf(ctx.reports, ctx.orgs);
    el.innerHTML = `
      <div class="section-title">기관별 서가</div>
      <div class="list">
        ${shelves.map((s) => `
          <a class="row" href="#/orgs/${encodeURIComponent(s.org)}">
            <div class="row__top">
              ${orgBadge(s.org)}
              <span class="row__series">${esc(s.name)}</span>
              <span class="row__date">${s.total}건</span>
            </div>
            <div class="row__authors">${s.series.length
              ? esc(s.series.map((x) => `${x.series} ${x.count}`).join(' · '))
              : '아직 수집 전'}</div>
          </a>`).join('')}
      </div>`;
    return;
  }

  const org = (ctx.orgs || []).find((o) => o.code === code);
  const rows = (ctx.reports || []).filter(
    (r) => r.org === code && (!series || r.series === series)
  ).sort((a, b) => (a.published < b.published ? 1 : -1));

  if (!series) {
    const s = shelf(ctx.reports, [org || { code, name: code }])[0];
    el.innerHTML = `
      <a class="back" href="#/orgs">← 기관</a>
      <div class="section-title">${esc(s.name)} · ${s.total}건</div>
      <div class="grid">
        ${s.series.map((x) => `
          <a class="tile" href="#/orgs/${encodeURIComponent(code)}/${encodeURIComponent(x.series)}">
            <div class="tile__name">${esc(x.series)}</div>
            <div class="tile__count">${x.count}건</div>
          </a>`).join('')}
      </div>
      ${s.total ? '' : empty('이 기관은 아직 수집되지 않았습니다.')}`;
    return;
  }

  el.innerHTML = `
    <a class="back" href="#/orgs/${encodeURIComponent(code)}">← ${esc(org ? org.name : code)}</a>
    <div class="section-title">${esc(series)} · ${rows.length}건</div>
    <div class="list">${rows.map((r) => reportRow(r)).join('')}</div>`;
}

// 보고서 상세. 원문은 기관 서버 링크로 내보내고 우리가 재배포하지 않는다 —
// 저작권 문제를 피하는 것도 있지만, 기관이 개정판을 올리면 링크 쪽이 자동으로
// 최신이 된다. 받아 두면 그 시점에 굳는다.
import { esc, dateLabel } from '../data.js';
import { orgBadge, empty } from '../ui.js';

export function detailModel(id, ctx) {
  const report = (ctx.reports || []).find((r) => r.id === id);
  if (!report) return null;
  const body = (ctx.abstracts && ctx.abstracts[report.id]) || null;
  const links = [];
  if (report.file_url) links.push({ label: '원문 PDF 열기', href: report.file_url });
  if (report.landing_url) links.push({ label: '기관 페이지 열기', href: report.landing_url });
  return {
    report,
    abstract: (body && body.abstract) || '',
    toc: (body && body.toc) || [],
    links,
  };
}

export function render(el, ctx) {
  const model = detailModel(ctx.route.params[0], ctx);
  if (!model) {
    el.innerHTML = empty('그 보고서를 찾을 수 없습니다.<br><a class="back" href="#/">검색으로</a>');
    return;
  }
  const r = model.report;
  const authors = (r.authors || []).join(', ');
  el.innerHTML = `
    <button class="back" type="button" id="back">← 뒤로</button>
    <div class="detail">
      <div class="row__top">
        ${orgBadge(r.org)}
        <span class="row__series">${esc(r.series || '')}</span>
        <span class="row__date">${esc(dateLabel(r.published, r.date_precision))}</span>
      </div>
      <h2 class="detail__title">${esc(r.title)}</h2>
      <div class="detail__meta">
        ${authors ? `저자 ${esc(authors)}<br>` : ''}
        ${r.pages ? `${r.pages}쪽<br>` : ''}
      </div>
      ${(r.matched || []).length ? `<div class="chips" style="padding-left:0">
        ${r.matched.map((t) => `<a class="chip" href="#/topics/${encodeURIComponent(t)}">${esc(t)}</a>`).join('')}
      </div>` : ''}
      <div class="detail__links">
        ${model.links.map((l, i) => `<a class="btn${i ? ' btn--ghost' : ''}"
             href="${esc(l.href)}" target="_blank" rel="noopener">${esc(l.label)}</a>`).join('')}
      </div>
      ${model.abstract ? `<h3>초록</h3><div class="detail__abstract">${esc(model.abstract)}</div>` : ''}
      ${model.toc.length ? `<details><summary><h3 style="display:inline">목차</h3></summary>
        <ul class="detail__toc">${model.toc.map((t) => `<li>${esc(t)}</li>`).join('')}</ul>
      </details>` : ''}
      ${!model.abstract && !model.toc.length
        ? '<div class="empty">이 보고서는 기관이 초록·목차를 공개하지 않습니다. 원문을 열어 보세요.</div>'
        : ''}
    </div>`;
  const back = el.querySelector('#back');
  if (back) back.addEventListener('click', () => window.history.back());
}

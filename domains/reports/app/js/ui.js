// 화면 조각. 어느 화면에서도 같은 모양으로 나와야 하는 것만 둔다.
import { esc, dateLabel, labelOf } from './data.js';

export function orgBadge(org) {
  const code = String(org || '').toLowerCase();
  return `<span class="org org--${esc(code)}">${esc(code.toUpperCase())}</span>`;
}

export function highlight(text, query) {
  const raw = String(text ?? '');
  const q = String(query ?? '').replace(/\s+/g, '');
  if (!q) return esc(raw);
  // 공백을 무시해 찾았으므로, 표시할 때도 사이에 공백이 끼어 있을 수 있다.
  const pattern = [...q].map((ch) => escapeRe(ch)).join('\\s*');
  try {
    return esc(raw).replace(new RegExp(pattern, 'gi'), (m) => `<mark>${m}</mark>`);
  } catch {
    return esc(raw);
  }
}

export function reportRow(report, { snippet = '', query = '', inGroup = false } = {}) {
  const authors = (report.authors || []).slice(0, 3).join(', ');
  const more = (report.authors || []).length > 3 ? ' 외' : '';
  return `
    <a class="row${inGroup ? ' row--in-group' : ''}" href="#/r/${encodeURIComponent(report.id)}">
      <div class="row__top">
        ${orgBadge(report.org)}
        ${report.picked ? '<span class="pick-badge">추천</span>' : ''}
        <span class="row__series">${esc(report.series || '')}</span>
        <span class="row__date">${esc(dateLabel(report.published, report.date_precision))}</span>
      </div>
      <div class="row__title">${highlight(report.title, query)}</div>
      ${authors ? `<div class="row__authors">${esc(authors + more)}</div>` : ''}
      ${snippet ? `<div class="row__snippet">${highlight(snippet, query)}</div>` : ''}
    </a>`;
}

export function foldRow(row) {
  return `
    <button class="fold" type="button" data-fold="${esc(row.id)}">
      <span>${row.open ? '▾' : '▸'}</span>
      <strong>${esc(row.label)}</strong>
      <span class="count">${row.count}건</span>
    </button>`;
}

export function chip(label, active, attrs = '') {
  return `<button class="chip${active ? ' chip--active' : ''}" type="button" ${attrs}>${esc(label)}</button>`;
}

export function empty(message) {
  return `<div class="empty">${message}</div>`;
}

export { labelOf };

function escapeRe(s) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

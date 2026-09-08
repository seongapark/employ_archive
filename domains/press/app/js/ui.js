// 여러 화면이 같이 쓰는 조각. 문자열을 만들고 붙이는 일만 한다.
import { esc, scale, timeLabel, dayLabel } from './data.js';

/** 회차 스위치. 셸이 한 번만 그리고 네 화면이 같은 것을 본다.
    회차가 매달 늘어나므로 버튼이 아니라 select 다. */
export function roundSwitchHtml(ctx) {
  const opts = ctx.rounds.map((r) => {
    const sel = r.release === ctx.state.release ? ' selected' : '';
    return `<option value="${esc(r.release)}"${sel}>${esc(r.label)} · ${esc(dayLabel(r.release))} 배포</option>`;
  }).join('');
  return `<select aria-label="회차 선택">${opts}</select>`;
}

export function bindRoundSwitch(el, ctx) {
  const sel = el.querySelector('select');
  if (!sel) return;
  sel.addEventListener('change', (e) => {
    ctx.state.release = e.target.value;
    ctx.rerender();
  });
}

/** 커버리지 막대 한 축. 0건은 빗금으로 남긴다 — 빈 칸은 사실을 안 보여준다. */
export function barGroup(title, rows) {
  const body = scale(rows).map((r) => `
    <div class="bar-row">
      <div class="bar-row__name">${esc(r.name)}</div>
      <div class="bar-row__track${r.n === 0 ? ' bar-row__track--zero' : ''}">
        ${r.n > 0 ? `<div class="bar-row__fill" style="width:${r.pct}%;"></div>` : ''}
      </div>
      <div class="bar-row__n num">${r.n}</div>
    </div>`).join('');
  return `<div style="margin-bottom:10px;">
    <div class="sec-title">${esc(title)}</div>
    <div class="bars">${body}</div>
  </div>`;
}

/** 기사 한 줄. 인용이 아닌 기사는 흐리게 두되 지우지는 않는다. */
export function articleRow(a) {
  const tags = (a.kw || []).slice(0, 2)
    .map((w) => `<span class="art__tag">${esc(w)}</span>`).join('');
  const why = !a.cites && a.why ? ` · ${esc(a.why)}` : '';
  const inner = `
    <div class="art__title">${esc(a.title)}${tags}</div>
    <div class="art__meta"><span>${esc(a.press)}</span><span class="num">${esc(timeLabel(a.pub))}</span><span>${why}</span></div>`;
  return a.url
    ? `<a class="art${a.cites ? '' : ' art--other'}" href="${esc(a.url)}" target="_blank" rel="noopener">${inner}</a>`
    : `<div class="art${a.cites ? '' : ' art--other'}">${inner}</div>`;
}

export function card(inner, style = '') {
  return `<div class="card" style="${style}">${inner}</div>`;
}

export function section(inner) {
  return `<div style="display:flex;flex-direction:column;gap:10px;padding:10px 16px 16px 16px;">${inner}</div>`;
}

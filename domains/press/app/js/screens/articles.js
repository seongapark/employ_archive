import { esc, roundOf, filterArticles } from '../data.js';
import { articleRow, section } from '../ui.js';

// 기사 화면은 '많이 보이는 것'이 목적이다. 카드로 감싸지 않고 한 줄씩 흘린다.
// 인용이 아닌 기사도 지우지 않는다 — 그날 무엇이 같이 돌았는지가 맥락이다.

function filterBar(round, ctx) {
  const kw = ctx.params.kw;
  const chips = [
    `<button type="button" class="pill${kw ? '' : ' pill--active'}" data-kw="" style="min-height:36px;">전체</button>`,
    ...round.outside.slice(0, 8).map((x) => `
      <button type="button" class="pill pill--frame${kw === x.w ? ' pill--active' : ''}"
        data-kw="${esc(x.w)}" style="min-height:36px;">${esc(x.w)} <span class="num">${x.n}</span></button>`),
  ].join('');
  return `<div style="display:flex;gap:6px;padding:8px 16px 4px 16px;overflow-x:auto;">${chips}</div>`;
}

function modeBar(round, ctx) {
  const hasFollow = Boolean(round.follow);
  const btn = (mode, label, on) => `<button type="button" class="pill${ctx.state.mode === mode ? ' pill--active' : ''}"
    data-mode="${mode}" style="min-height:36px;${on ? '' : 'opacity:.45;'}" ${on ? '' : 'disabled'}>${esc(label)}</button>`;
  const toggle = `<button type="button" class="pill${ctx.state.onlyCited ? ' pill--active' : ''}"
    data-toggle="cited" style="min-height:36px;margin-left:auto;">인용만</button>`;
  return `<div style="display:flex;gap:6px;padding:4px 16px 0 16px;align-items:center;">
    ${btn('regular', '정기', true)}${btn('follow', '후속', hasFollow)}${toggle}</div>`;
}

export function render(root, ctx) {
  const round = roundOf(ctx.rounds, ctx.state.release);
  if (!round) {
    root.innerHTML = '<div class="empty">회차가 없습니다.</div>';
    return;
  }
  if (ctx.state.mode === 'follow' && !round.follow) ctx.state.mode = 'regular';

  const bundle = ctx.articles[round.release] || { regular: [], follow: [] };
  const all = bundle[ctx.state.mode] || [];
  const shown = filterArticles(all, { onlyCited: ctx.state.onlyCited, kw: ctx.params.kw });

  const head = ctx.state.mode === 'follow'
    ? `후속 ${round.follow ? round.follow.window.join(' ~ ') : ''}`
    : `정기 ${round.regular.window.join(' ~ ')}`;
  const count = `${shown.length}건`
    + (ctx.state.onlyCited ? ` · 인용 아닌 ${all.length - all.filter((a) => a.cites).length}건 숨김` : '');

  const list = shown.length
    ? shown.map(articleRow).join('')
    : '<div class="empty">해당하는 기사가 없습니다.</div>';

  root.innerHTML = `
        ${modeBar(round, ctx)}
    ${filterBar(round, ctx)}
    ${section(`
      <div style="font-size:11px;color:var(--text-muted);margin:0 0 -4px 2px;">
        <span class="num">${esc(head)}</span> · <span class="num">${esc(count)}</span></div>
      <div class="card" style="padding:2px 14px;">${list}</div>
    `)}`;

  root.querySelectorAll('[data-kw]').forEach((el) => {
    el.addEventListener('click', () => {
      const w = el.dataset.kw;
      ctx.navigate(w ? `#/articles/${encodeURIComponent(w)}` : '#/articles');
    });
  });
  root.querySelectorAll('[data-mode]').forEach((el) => {
    el.addEventListener('click', () => {
      ctx.state.mode = el.dataset.mode;
      ctx.rerender();
    });
  });
  const toggle = root.querySelector('[data-toggle="cited"]');
  if (toggle) {
    toggle.addEventListener('click', () => {
      ctx.state.onlyCited = !ctx.state.onlyCited;
      ctx.rerender();
    });
  }
}

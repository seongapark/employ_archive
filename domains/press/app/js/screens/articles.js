import { esc, roundOf, filterArticles } from '../data.js';
import { articleRow, card, section } from '../ui.js';
import { graphSvg, legendHtml } from '../graph.js';

// 배포 당일(정기) 보도만 다룬다. 그 뒤 보름은 후속 화면이 맡는다.
//
// 네트워크가 맨 위에 있는 이유: 이 화면의 지도다. 점을 누르면 바로 아래
// 목록이 그 말로 걸러진다 — 그림과 목록이 떨어져 있으면 둘을 잇는 것은
// 사람 몫이 된다.
//
// 인용이 아닌 기사도 지우지 않는다. 그날 무엇이 같이 돌았는지가 맥락이다.

function netCard(round, ctx) {
  const g = round.graph;
  if (!g || !g.nodes.length) return '';
  const trimmed = g.trimmed ? ` · 적게 나온 ${g.trimmed}개는 뺐습니다` : '';
  const picked = ctx.params.kw
    ? `<div style="font-size:11px;color:var(--frame-fg);margin-top:4px;">
         아래 목록은 「${esc(ctx.params.kw)}」로 걸러져 있습니다 ·
         <a href="#/articles">전체로</a></div>` : '';
  return card(`
    <div style="font-size:13px;font-weight:700;">이 달 보도가 묶인 모양</div>
    <div style="font-size:11px;color:var(--text-secondary);margin:2px 0 6px;">
      한 기사에 같이 나온 말끼리 이었습니다 · 점 크기는 기사 수, 선 굵기는 같이 나온 횟수</div>
    ${graphSvg(g)}
    <div style="font-size:10px;color:var(--text-muted);margin-top:4px;">${legendHtml(g)}</div>
    <div style="font-size:10px;color:var(--text-muted);margin-top:4px;">
      점을 누르면 그 말이 든 기사만 남습니다${trimmed}</div>
    ${picked}`);
}

function filterBar(round, ctx) {
  const kw = ctx.params.kw;
  const chips = [
    `<button type="button" class="pill${kw ? '' : ' pill--active'}" data-kw="" style="min-height:36px;">전체</button>`,
    ...round.outside.slice(0, 8).map((x) => `
      <button type="button" class="pill pill--frame${kw === x.w ? ' pill--active' : ''}"
        data-kw="${esc(x.w)}" style="min-height:36px;">${esc(x.w)} <span class="num">${x.n}</span></button>`),
  ].join('');
  const toggle = `<button type="button" class="pill${ctx.state.onlyCited ? ' pill--active' : ''}"
    data-toggle="cited" style="min-height:36px;">인용만</button>`;
  return `<div style="display:flex;gap:6px;padding:8px 16px 0 16px;overflow-x:auto;">
    ${toggle}${chips}</div>`;
}

export function render(root, ctx) {
  const round = roundOf(ctx.rounds, ctx.state.release);
  if (!round) {
    root.innerHTML = '<div class="empty">회차가 없습니다.</div>';
    return;
  }

  const bundle = ctx.articles[round.release] || { regular: [] };
  const all = bundle.regular || [];
  const shown = filterArticles(all, { onlyCited: ctx.state.onlyCited, kw: ctx.params.kw });
  const hidden = all.length - all.filter((a) => a.cites).length;

  const head = `배포 당일 ${round.regular.window.join(' ~ ')}`;
  const count = `${shown.length}건`
    + (ctx.state.onlyCited && hidden ? ` · 인용 아닌 ${hidden}건 숨김` : '');

  const list = shown.length
    ? shown.map(articleRow).join('')
    : '<div class="empty">해당하는 기사가 없습니다.</div>';

  root.innerHTML = `
    ${filterBar(round, ctx)}
    ${section(`
      ${netCard(round, ctx)}
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
  const toggle = root.querySelector('[data-toggle="cited"]');
  if (toggle) {
    toggle.addEventListener('click', () => {
      ctx.state.onlyCited = !ctx.state.onlyCited;
      ctx.rerender();
    });
  }
}

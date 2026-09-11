import { esc, roundOf, filterArticles } from '../data.js';
import { articleRow, card, section } from '../ui.js';
import { graphSvg, legendHtml, applyPick } from '../graph.js';

// 배포 당일(정기) 보도만 다룬다. 그 뒤 보름은 후속 화면이 맡는다.
//
// 그래프가 맨 위에 있는 이유: 이 화면의 지도다. 점을 누르면 바로 아래
// 목록이 그 말로 걸러진다 — 그림과 목록이 떨어져 있으면 둘을 잇는 것은
// 사람 몫이 된다.
//
// **필터 버튼 줄은 2026-09-11 에 뺐다.** 점이 곧 필터인데 그 위에 같은 말을
// 담은 칩이 또 있었다. 두 장치가 같은 일을 하면 어느 쪽을 눌러야 하는지 알 수
// 없고, 눌렀을 때 다른 쪽이 안 따라오면 화면이 거짓말을 한다.
//
// 인용이 아닌 기사도 지우지 않는다. 그날 무엇이 같이 돌았는지가 맥락이다.

function netCard(round, ctx) {
  const g = round.graph;
  if (!g || !g.nodes.length) return '';
  return card(`
    <div style="font-size:13px;font-weight:700;margin-bottom:6px;">키워드그래프</div>
    ${graphSvg(g, { selected: ctx.params.kw })}
    <div style="font-size:11px;color:var(--text-secondary);margin-top:6px;">
      한 기사에 같이 나온 키워드를 이어 표현 · 점 크기는 기사 수, 선 굵기는 같이 나온 횟수</div>
    <div style="font-size:10px;color:var(--text-muted);margin-top:5px;">${legendHtml(g)}</div>`);
}

export function render(root, ctx) {
  const round = roundOf(ctx.rounds, ctx.state.release);
  if (!round) {
    root.innerHTML = '<div class="empty">회차가 없습니다.</div>';
    return;
  }

  const bundle = ctx.articles[round.release] || { regular: [] };
  const all = bundle.regular || [];

  root.innerHTML = `
    ${section(`
      ${netCard(round, ctx)}
      <div class="artmeta" id="artMeta"></div>
      <div class="card" style="padding:2px 14px;" id="artList"></div>
    `)}`;

  const listEl = root.querySelector('#artList');
  const metaEl = root.querySelector('#artMeta');

  function paint() {
    const kw = ctx.params.kw;
    const shown = filterArticles(all, { onlyCited: ctx.state.onlyCited, kw });
    const other = filterArticles(all, { onlyCited: false, kw }).length - shown.length;
    const head = `배포 당일 ${round.regular.window.join(' ~ ')}`;

    // 「인용만」 토글은 버튼 줄에서 이 한 줄로 옮겼다. 기능은 남기고 장치만 줄인다 —
    // 그날 같이 돈 기사를 볼 길이 없으면 낮은 인용률이 무슨 뜻인지 알 수 없다.
    const toggle = ctx.state.onlyCited
      ? (other ? ` · <a href="#" data-toggle="cited">딴 얘기 ${other}건 함께 보기</a>` : '')
      : ' · <a href="#" data-toggle="cited">인용만 보기</a>';
    const picked = kw
      ? ` · 「${esc(kw)}」로 걸러짐 <a href="#" data-clear="1">전체로</a>` : '';

    metaEl.innerHTML = `<span class="num">${esc(head)}</span>`
      + ` · <span class="num">${shown.length}건</span>${toggle}${picked}`;
    listEl.innerHTML = shown.length
      ? shown.map(articleRow).join('')
      : '<div class="empty">해당하는 기사가 없습니다.</div>';

    metaEl.querySelectorAll('[data-toggle="cited"]').forEach((el) => {
      el.addEventListener('click', (e) => {
        e.preventDefault();
        ctx.state.onlyCited = !ctx.state.onlyCited;
        paint();
      });
    });
    metaEl.querySelectorAll('[data-clear]').forEach((el) => {
      el.addEventListener('click', (e) => { e.preventDefault(); pick(null); });
    });
  }

  // 점을 눌러도 화면을 통째로 다시 그리지 않는다. innerHTML 을 갈아끼우면
  // CSS 전환이 안 먹어서 그림이 툭 바뀌고, 스크롤도 맨 위로 튄다.
  // 주소는 replaceState 로 조용히 맞춰 둔다 — hashchange 가 안 나므로
  // 라우터가 다시 돌지 않는다.
  const svg = root.querySelector('.gnet');
  function pick(kw) {
    ctx.params = { ...ctx.params, kw };
    const hash = kw ? `#/articles/${encodeURIComponent(kw)}` : '#/articles';
    history.replaceState(null, '', hash);
    applyPick(svg, round.graph, kw);
    paint();
  }

  if (svg) {
    svg.querySelectorAll('[data-kw]').forEach((el) => {
      el.addEventListener('click', (e) => {
        e.preventDefault();
        const w = el.dataset.kw;
        pick(w === ctx.params.kw ? null : w);   // 같은 점을 다시 누르면 풀린다
      });
    });
  }

  paint();
}

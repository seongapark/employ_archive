// 보도자료 화면. 총괄 카드를 누르면 여기로 온다.
//
// 누른 카드를 그대로 맨 위에 다시 그린다(overview 의 cardHtml 을 빌려 쓴다).
// 화면을 바꾸면서 방금 본 숫자가 사라지면, 요약을 읽는 동안 그 요약이 무엇에
// 대한 것인지를 기억으로만 붙들어야 한다.

import { switcherHtml, bindSwitcher } from '../switcher.js';
import { cardHtml } from './overview.js';
import {
  overviewCards, topMovers, segmentsOf, fmtDelta, deltaTone, monthLabel, esc,
} from '../data.js';

// 요약 줄의 머리글자가 원문의 층을 말한다. 글머리표를 우리가 새로 달지 않고
// (□ 를 <ul> 에 넣으면 점이 두 개가 된다) 들여쓰기만 층에 맞춰 준다.
const DEPTH = { '□': 1, '▣': 1, '○': 2, 'ㅇ': 2, '-': 2, '*': 3, '▸': 3 };

function digestHtml(card) {
  const lines = card.summaryLines || [];
  if (!lines.length) {
    // 지어내지 않는다. 아직 안 읽은 달과 원문 형식이 바뀐 달이 여기로 온다.
    return `<p class="digest__empty">이 달 요약은 아직 없습니다.
      <a href="${esc(card.releaseUrl)}" rel="noopener">보도자료 원문</a>에서 확인해 주세요.</p>`;
  }
  return lines.map(line =>
    `<p class="digest__line" data-depth="${DEPTH[line.slice(0, 1)] || 1}">${esc(line)}</p>`
  ).join('');
}

function moversHtml(groups, card) {
  if (!groups.length) return '';
  const block = group => {
    const rows = group.rows.map(row => {
      const label = esc(row.short_ko || row.name_ko);
      // 그 분류의 세 출처 비교로 이어진다 — 여기서 본 숫자가 다른 조사에서는
      // 어떻게 나오는지가 이 앱의 본래 질문이다.
      const href = `#/b/${esc(group.breakdown)}/${encodeURIComponent(row.code)}`;
      return `<a class="mover" href="${href}">
        <span class="mover__name">${label}</span>
        <span class="mover__delta num ${deltaTone(row.yoy)}">${esc(fmtDelta(row.yoy))}</span>
      </a>`;
    }).join('');
    return `<div class="movers__group">
      <h3 class="movers__title">${esc(group.name_ko)}</h3>
      <div class="movers__rows">${rows}</div>
    </div>`;
  };
  return `<section class="movers">
    <h2 class="section__title">${esc(monthLabel(card.period))} 가장 크게 움직인 곳</h2>
    ${groups.map(block).join('')}
    <p class="movers__note">전년동월대비 증감 · 누르면 세 출처를 나란히 봅니다</p>
  </section>`;
}

export function render(el, ctx) {
  const code = ctx.state.releaseCode;
  const cards = overviewCards(ctx.series, ctx.sources, ctx.state.period, ctx.releases);
  const card = cards.find(c => c.code === code);
  if (!card) {                       // 라우트가 걸렀어야 하지만, 화면이 먼저 죽지는 않는다
    el.innerHTML = '<p class="note">알 수 없는 출처입니다. <a href="#/">총괄로</a></p>';
    return;
  }

  const groups = topMovers(ctx.series, {
    source: code, period: ctx.state.period,
    segments: segmentsOf(ctx.industries, ctx.segments),
  });

  el.innerHTML = `<a class="backlink" href="#/">
      <span aria-hidden="true">←</span> 총괄</a>`
    + switcherHtml(ctx)
    // 여기서는 카드가 문이 아니다. 이미 그 방 안이므로 이름을 링크로 두면
    // 같은 화면으로 가는 링크가 된다.
    + `<div class="cards">${cardHtml(card, { linked: false })}</div>`
    + `<section class="digest">
        <h2 class="section__title">보도자료 요약</h2>
        ${digestHtml(card)}
        ${card.summaryLines.length
          ? `<p class="digest__note">${esc(card.name_ko)} 보도자료 원문의 요약을 그대로 옮긴 것입니다.</p>`
          : ''}
      </section>`
    + moversHtml(groups, card);

  bindSwitcher(el, ctx);
}

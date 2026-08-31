import { overviewCards, fmtLevel, fmtDelta, monthLabel, esc } from '../data.js';

function switcher(ctx) {
  const { years, monthsByYear } = ctx.months;
  const year = Number(ctx.state.period.slice(0, 4));
  const month = Number(ctx.state.period.slice(5, 7));
  const yearOpts = years.map(y =>
    `<option value="${y}"${y === year ? ' selected' : ''}>${y}년</option>`).join('');
  const monthOpts = (monthsByYear[year] || []).map(m =>
    `<option value="${m}"${m === month ? ' selected' : ''}>${m}월</option>`).join('');
  return `<div class="switcher">
    <select id="yearSelect" aria-label="기준 연도">${yearOpts}</select>
    <select id="monthSelect" aria-label="기준 월">${monthOpts}</select>
  </div>`;
}

// 사업체노동력조사의 released_at 은 보도자료 발표일이 아니라 KOSIS 표 갱신일이다.
// 다른 둘과 뜻이 다르므로 라벨을 달리 쓴다.
function releaseLabel(card) {
  const at = card.releasedAt;
  if (!at) return '';
  const when = `${at.slice(5, 7)}.${at.slice(8, 10)}`;
  return card.code === 'est' ? `KOSIS 갱신 ${when}` : `발표 ${when}`;
}

function attachmentLinks(card) {
  return (card.attachments || [])
    .map(a => `<a href="${esc(a.url)}" rel="noopener">${esc(a.type)}</a>`).join(' · ');
}

function cardHtml(card) {
  const head = `<div class="card__head"><span class="card__name">${esc(card.name_ko)}</span>
    <span class="card__meta num">${esc(releaseLabel(card))}</span></div>`;

  const body = card.state === 'value'
    ? `<div class="card__value num">${esc(fmtLevel(card.value))}</div>
       <div class="card__delta num ${card.yoy >= 0 ? 'is-up' : 'is-down'}">${esc(fmtDelta(card.yoy))} <span class="card__deltaNote">전년동월대비</span></div>`
    : `<div class="card__value card__value--empty">${esc(monthLabel(card.period))} 기준 미발표</div>` +
      (card.fallback
        ? `<div class="card__fallback num">최신 ${esc(monthLabel(card.fallback.period))} · ${esc(fmtLevel(card.fallback.value))} (${esc(fmtDelta(card.fallback.yoy))})</div>`
        : '');

  // coverage 는 접히지 않는다. 정의 차이의 인지가 이 앱의 핵심 가치다(스펙 7.5).
  const coverage = `<div class="card__coverage">${esc(card.coverage)}</div>`;
  const links = `<div class="card__links"><a href="${esc(card.releaseUrl)}" rel="noopener">원문보기</a>${
    attachmentLinks(card) ? ' · ' + attachmentLinks(card) : ''}</div>`;

  return `<article class="card" data-source="${esc(card.code)}">${head}${body}${coverage}${links}</article>`;
}

export function render(el, ctx) {
  const cards = overviewCards(ctx.series, ctx.sources, ctx.state.period);
  el.innerHTML = switcher(ctx) + `<div class="cards">${cards.map(cardHtml).join('')}</div>`;

  el.querySelector('#yearSelect').addEventListener('change', e => {
    const year = Number(e.target.value);
    const months = ctx.months.monthsByYear[year] || [];
    const month = months[months.length - 1];
    ctx.state.period = `${year}-${String(month).padStart(2, '0')}`;
    ctx.rerender();
  });
  el.querySelector('#monthSelect').addEventListener('change', e => {
    ctx.state.period = `${ctx.state.period.slice(0, 4)}-${String(e.target.value).padStart(2, '0')}`;
    ctx.rerender();
  });
}

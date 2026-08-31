import { overviewCards, fmtLevel, fmtDelta, deltaTone, monthLabel, EMPTY_LABEL, esc } from '../data.js';

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

// 증감 줄. state 는 data.js 의 cellState 가 이미 판정했다 — 여기서는 그릴 뿐이다.
// noDelta 는 숫자가 아니라 `증감없음` 이다. fmtDelta(null) 을 그리면 시트가
// `― 증감없음` 이라 말하는 같은 사실을 카드는 `0.0만명 증가` 로 말하게 된다.
function deltaRow(card) {
  if (card.state === 'noDelta') {
    return `<div class="card__delta is-flat">${esc(EMPTY_LABEL.noDelta)} <span class="card__deltaNote">전년동월대비</span></div>`;
  }
  return `<div class="card__delta num ${deltaTone(card.yoy)}">${esc(fmtDelta(card.yoy))} <span class="card__deltaNote">전년동월대비</span></div>`;
}

function cardHtml(card) {
  // 잠정/확정 배지는 스펙 5장·상위 7.5 가 카드에 요구한다. 지금 적재분은 전부 `잠정` 이다.
  const badge = card.status
    ? ` <span class="badge badge--status">${esc(card.status)}</span>` : '';
  const head = `<div class="card__head"><span class="card__name">${esc(card.name_ko)}${badge}</span>
    <span class="card__meta num">${esc(releaseLabel(card))}</span></div>`;

  const body = card.state === 'unpublished'
    ? `<div class="card__value card__value--empty">${esc(monthLabel(card.period))} 기준 미발표</div>` +
      (card.fallback
        ? `<div class="card__fallback num">최신 ${esc(monthLabel(card.fallback.period))} · ${esc(fmtLevel(card.fallback.value))} (${esc(
            card.fallback.state === 'noDelta' ? EMPTY_LABEL.noDelta : fmtDelta(card.fallback.yoy))})</div>`
        : '')
    : `<div class="card__value num">${esc(fmtLevel(card.value))}</div>
       ${deltaRow(card)}`;

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

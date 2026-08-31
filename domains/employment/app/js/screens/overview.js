import { switcherHtml, bindSwitcher } from '../switcher.js';
import { overviewCards, fmtLevel, fmtDelta, deltaTone, monthLabel, EMPTY_LABEL, esc } from '../data.js';

// 사업체노동력조사의 released_at 은 보도자료 발표일이 아니라 KOSIS 표 갱신일이다.
// 다른 둘과 뜻이 다르므로 라벨을 달리 쓴다.
function releaseLabel(card) {
  const at = card.releasedAt;
  if (!at) return '';
  const when = `${at.slice(5, 7)}.${at.slice(8, 10)}`;
  return card.code === 'est' ? `KOSIS 갱신 ${when}` : `발표 ${when}`;
}

// 첨부는 눌러서 바로 받는다. download 속성은 다른 도메인 파일에는 브라우저가
// 무시하지만(게시판이 Content-Disposition 을 주므로 실제로는 내려받아진다),
// 링크가 무엇인지 이름으로 밝히는 편이 낫다.
const ATTACH_LABEL = { hwpx: '한글', hwp: '한글', pdf: 'PDF', xlsx: '엑셀' };

function attachmentLinks(card) {
  return (card.attachments || []).map(a =>
    `<a class="card__file" href="${esc(a.url)}" rel="noopener" download>${
      esc(ATTACH_LABEL[a.type] || a.type)} 받기</a>`).join('');
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
  // 보도자료는 그 출처의 게시판 검색 결과로 보낸다. 지금 레코드가 들고 있는
  // release_url 은 수집한 회차(=최신월) 게시글 하나뿐이라, 과거 달에서 누르면
  // 다른 달의 글이 열린다. 달마다 게시글을 찾아 넣기 전까지는 목록이 정확하다.
  const parts = [`<a class="card__go" href="${esc(card.releaseUrl)}" rel="noopener">보도자료</a>`];
  if (card.kosisUrl) {
    parts.push(`<a class="card__go" href="${esc(card.kosisUrl)}" rel="noopener">KOSIS</a>`);
  }
  const files = attachmentLinks(card);
  const links = `<div class="card__links">${parts.join('')}${files}</div>`;

  return `<article class="card" data-source="${esc(card.code)}">${head}${body}${coverage}${links}</article>`;
}

export function render(el, ctx) {
  const cards = overviewCards(ctx.series, ctx.sources, ctx.state.period, ctx.releases);
  el.innerHTML = switcherHtml(ctx) + `<div class="cards">${cards.map(cardHtml).join('')}</div>`;

  bindSwitcher(el, ctx);
}

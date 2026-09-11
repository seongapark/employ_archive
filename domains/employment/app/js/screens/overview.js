import { switcherHtml, bindSwitcher } from '../switcher.js';
import { overviewCards, fmtLevel, fmtDelta, deltaTone, monthLabel, EMPTY_LABEL, esc } from '../data.js';

// 사업체노동력조사의 released_at 은 보도자료 발표일이 아니라 KOSIS 표 갱신일이다.
// 다른 둘과 뜻이 다르므로 라벨을 달리 쓴다.
// 날짜의 뜻이 레코드마다 다르다. KOSIS 표에서 받은 값이면 표가 갱신된 날이고,
// 보도자료에서 읽은 값이면 발표일이다. 사업체노동력조사는 과거 달을 KOSIS 에서,
// 최신월을 보도자료에서 받으므로 한 출처 안에서도 갈린다 — 출처 이름으로
// 판단하면 보도자료에서 온 값에 `KOSIS 갱신` 이라 적히게 된다.
function releaseLabel(card) {
  const at = card.releasedAt;
  if (!at) return '';
  const when = `${at.slice(5, 7)}.${at.slice(8, 10)}`;
  return card.origin === 'kosis' ? `KOSIS 갱신 ${when}` : `발표 ${when}`;
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

export function cardHtml(card, { linked = true } = {}) {
  // 잠정/확정 배지를 그리지 않는다(스펙 5장·상위 7.5 는 이걸 요구했다).
  //
  // 세 수집기 어디에도 status 를 넘기는 곳이 없어 2,082개 레코드가 전부 기본값
  // `잠정` 이었다. 그 배지는 "이 값이 잠정이다" 가 아니라 "우리가 확인한 적 없다"
  // 를 표시하고 있었고, 모든 카드에 똑같이 붙으니 아무것도 구분하지 못했다.
  //
  // 대신 이 앱은 숫자를 두 갈래로 대조한다 — 달마다 그 달의 보도자료로 링크를
  // 걸고(releases.json), KOSIS 표의 값이 보도자료와 어긋나면 수집이 실패한다
  // (check_kosis). 근거 없는 배지보다 이쪽이 실제 보증이다.
  //
  // 되살리려면 배지를 다시 그리기 전에 수집기가 원문에서 잠정/확정을 읽어
  // status 로 넘겨야 한다. 레코드의 status 필드는 그때를 위해 남겨 둔다.
  // 카드 전체가 보도자료 화면으로 가는 문이다. 다만 카드를 통째로 <a> 로 감쌀
  // 수는 없다 — 안에 보도자료·KOSIS·첨부 링크가 이미 있고, 링크 안의 링크는
  // 없는 문법이다(브라우저가 바깥 <a> 를 잘라 카드가 조각난다).
  // 그래서 **이름만 진짜 링크**로 두고(키보드·스크린리더가 지나는 길) 카드
  // 전체의 탭은 render() 의 위임 핸들러가 받는다.
  const name = linked
    ? `<a class="card__name card__open" href="#/r/${esc(card.code)}">${esc(card.name_ko)}<span class="card__chev" aria-hidden="true">›</span></a>`
    : `<span class="card__name">${esc(card.name_ko)}</span>`;
  const head = `<div class="card__head">${name}
    <span class="card__meta num">${esc(releaseLabel(card))}</span></div>`;

  // 숫자의 이름. 세 출처가 저마다 다른 것을 센다 — 취업자수·종사자수·상시가입자수 —
  // 이고, 그 차이를 보여주는 것이 이 앱의 요점이다. 이름이 없으면 숫자 바로 밑의
  // 포괄범위 줄(`15세 이상 인구 · 조사대상주간 …`)이 이름표처럼 읽혀서 취업자수를
  // 인구수로 보게 된다(2026-09-11 사용자가 짚었다). 미발표인 달에도 남긴다 —
  // 이름이 같이 사라지면 무엇의 미발표인지 알 수 없다.
  const headline = card.headline_ko
    ? `<div class="card__headline">${esc(card.headline_ko)}</div>` : '';

  const body = headline + (card.state === 'unpublished'
    ? `<div class="card__value card__value--empty">${esc(monthLabel(card.period))} 기준 미발표</div>` +
      (card.fallback
        ? `<div class="card__fallback num">최신 ${esc(monthLabel(card.fallback.period))} · ${esc(fmtLevel(card.fallback.value))} (${esc(
            card.fallback.state === 'noDelta' ? EMPTY_LABEL.noDelta : fmtDelta(card.fallback.yoy))})</div>`
        : '')
    : `<div class="card__value num">${esc(fmtLevel(card.value))}</div>
       ${deltaRow(card)}`);

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
  el.innerHTML = switcherHtml(ctx)
    + `<div class="cards">${cards.map(card => cardHtml(card)).join('')}</div>`;

  bindSwitcher(el, ctx);

  // 카드 어디를 눌러도 보도자료 화면으로 간다. 안쪽 링크(보도자료·KOSIS·첨부)를
  // 누른 것이면 비켜 준다 — 첨부 받기는 총괄에 그대로 두기로 했으므로, 이 한 줄이
  // 없으면 파일을 받으려던 손가락이 화면 전환에 먹힌다.
  el.querySelector('.cards')?.addEventListener('click', e => {
    if (e.target.closest('a')) return;
    const card = e.target.closest('.card');
    if (card && card.dataset.source) location.hash = `#/r/${card.dataset.source}`;
  });
}

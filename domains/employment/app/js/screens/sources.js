import { esc, SOURCE_ORDER, SOURCE_COLORS } from '../data.js';

// 시트에서 사업체노동력조사 선이 늦게 시작하는 이유는 결함이 아니라 사실이다.
// 근거를 이 화면에 둔다(상위 스펙 11장).
const NOTES = [
  ['시계열이 시작하는 달이 다르다',
   '사업체노동력조사의 전년동월대비는 2025년 1월부터다. 2024년 1월 이전은 다른 산업분류 체계의 별도 표에 있고, 이어붙이면 재분류 효과가 고용 변화로 둔갑하므로 잇지 않는다. 짧은 선이 틀린 선보다 낫다.'],
  ['성·연령별은 두 출처만 있다',
   '사업체노동력조사는 성·연령별 종사자수를 공표하지 않는다. 그 단면에서는 경제활동인구조사와 고용행정통계 둘만 비교된다.'],
  ['같은 분류를 다르게 부른다',
   '경제활동인구조사는 남자·여자·15∼29세로, 고용행정통계는 남성·여성·29세이하로 쓴다. 이 앱은 남자·여자·29세 이하로 통일해 표기한다.'],
];

export function render(el, ctx) {
  const cards = SOURCE_ORDER.map(code => {
    const meta = ctx.sources.find(s => s.code === code);
    if (!meta) return '';
    return `<article class="scard">
      <div class="scard__head"><span class="swatch" style="background:${esc(SOURCE_COLORS[code])}"></span>
        <span class="scard__name">${esc(meta.name_ko)}</span>
        <span class="scard__agency">${esc(meta.agency)}</span></div>
      <dl class="scard__defs">
        <dt>대표 지표</dt><dd>${esc(meta.headline_ko)}</dd>
        <dt>조사 성격</dt><dd>${esc(meta.type)}</dd>
        <dt>포괄 범위</dt><dd>${esc(meta.coverage)}</dd>
        <dt>발표 주기</dt><dd>${esc(meta.release_rule)}</dd>
        <dt>유의사항</dt><dd>${esc(meta.caveat)}</dd>
      </dl>
      <a class="scard__link" href="${esc(meta.board_url)}" rel="noopener">게시판 바로가기</a>
    </article>`;
  }).join('');

  const notes = NOTES.map(([title, body]) =>
    `<section class="note"><h3>${esc(title)}</h3><p>${esc(body)}</p></section>`).join('');

  el.innerHTML = `<div class="scards">${cards}</div>${notes}`;
}

import { esc, shortOf, SOURCE_ORDER, SOURCE_COLORS } from '../data.js';

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

// 행 정의: [머리, 그 출처에서 값을 꺼내는 함수]. 표를 세로로 읽으면 한 출처의
// 정의가, 가로로 읽으면 세 출처가 같은 항목에서 어떻게 갈리는지 보인다 —
// 가로로 읽히는 것이 이 화면의 목적이므로 항목을 행에 둔다.
const ROWS = [
  ['정식 명칭', m => m.name_ko],
  ['기관', m => m.agency],
  ['대표 지표', m => m.headline_ko],
  ['조사 성격', m => m.type],
  ['발표 주기', m => m.release_rule],
  ['포괄 범위', m => m.coverage],
  ['유의사항', m => m.caveat],
];

function sexAgeRow(ctx) {
  // 성·연령 제공 여부는 segments.json 이 이미 알고 있다. 화면에서 다시 판정하지 않는다.
  const sex = (ctx.segments || []).find(s => s.breakdown === 'sex');
  const provided = sex && sex.categories.length ? sex.categories[0].provided : null;
  const cells = SOURCE_ORDER.map(code => {
    const ok = provided ? provided[code] : null;
    return `<td class="${ok ? '' : 'cell--empty'}">${ok ? '제공' : '미제공'}</td>`;
  }).join('');
  return `<tr><th scope="row">성·연령별</th>${cells}</tr>`;
}

export function render(el, ctx) {
  const metas = SOURCE_ORDER.map(code => ctx.sources.find(s => s.code === code)).filter(Boolean);

  const head = `<thead><tr><th scope="col">항목</th>${
    metas.map(m => `<th scope="col">
      <span class="swatch" style="background:${esc(SOURCE_COLORS[m.code])}"></span>
      ${esc(shortOf(m))}</th>`).join('')
  }</tr></thead>`;

  const body = ROWS.map(([label, pick]) =>
    `<tr><th scope="row">${esc(label)}</th>${
      metas.map(m => `<td>${esc(pick(m) || '')}</td>`).join('')
    }</tr>`).join('') + sexAgeRow(ctx) +
    `<tr><th scope="row">원문</th>${
      metas.map(m => `<td><a href="${esc(m.board_url)}" rel="noopener">게시판</a></td>`).join('')
    }</tr>`;

  const notes = NOTES.map(([title, body2]) =>
    `<section class="note"><h3>${esc(title)}</h3><p>${esc(body2)}</p></section>`).join('');

  el.innerHTML = `
    <p class="rotate-hint">가로로 돌리면 세 출처가 한눈에 들어옵니다.</p>
    <div class="stable__wrap"><table class="stable">${head}<tbody>${body}</tbody></table></div>
    ${notes}`;
}

import { esc, shortOf, SOURCE_ORDER, SOURCE_COLORS } from '../data.js';

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
      metas.map(m => `<td><a href="${esc(m.board_url)}" rel="noopener">보도자료</a>${
        m.kosis_url ? ` · <a href="${esc(m.kosis_url)}" rel="noopener">KOSIS</a>` : ''
      }</td>`).join('')
    }</tr>`;

  el.innerHTML = `
    <p class="rotate-hint">옆으로 밀면 세 출처를 나란히 볼 수 있습니다 · 가로로 돌리면 한눈에 들어옵니다</p>
    <div class="stable__frame">
      <div class="stable__wrap"><table class="stable">${head}<tbody>${body}</tbody></table></div>
    </div>`;

  // 오른쪽 끝까지 밀면 페이드를 끈다. 계속 띄워두면 "더 있다" 고 거짓말하게 된다.
  const wrap = el.querySelector('.stable__wrap');
  const frame = el.querySelector('.stable__frame');
  const sync = () => {
    const more = wrap.scrollWidth - wrap.clientWidth - wrap.scrollLeft > 4;
    frame.classList.toggle('stable__frame--more', more);
  };
  wrap.addEventListener('scroll', sync, { passive: true });
  sync();
}

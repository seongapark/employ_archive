import {
  segmentsOf, breakdownMatrix, categoryTimeline, fmtDelta, deltaTone, monthLabel,
  EMPTY_LABEL, emptyLabel, esc, SOURCE_ORDER, SOURCE_COLORS,
} from '../data.js';

// 사업체노동력조사가 성·연령에서 통째로 비는 이유를 화면이 말한다.
// 열을 지우면 "안 잡는다"는 사실 자체가 사라진다.
const EST_NOTE = '사업체노동력조사는 성·연령별 종사자수를 공표하지 않습니다.';

function tabs(segments, current) {
  return `<div class="btabs">${segments.map(s =>
    `<a class="btab${s.breakdown === current ? ' btab--active' : ''}" href="#/b/${s.breakdown}">${esc(s.name_ko)}</a>`
  ).join('')}</div>`;
}

function cell(state, yoy) {
  if (state === 'value') {
    return `<td class="num ${deltaTone(yoy)}">${esc(fmtDelta(yoy))}</td>`;
  }
  // 매트릭스 칸은 좁으므로 `― ` 없이 문구만 쓴다. 문구 자체는 data.js 가 갖는다.
  return `<td class="cell--empty">${esc(EMPTY_LABEL[state] || '―')}</td>`;
}

export function render(el, ctx) {
  const segments = segmentsOf(ctx.industries, ctx.segments);
  const current = ctx.state.breakdown || 'industry';
  const segment = segments.find(s => s.breakdown === current) || segments[0];
  const sort = ctx.state.sort || 'delta';
  // breakdown 은 필수 인자다 — 산업 F(건설업)와 성별 F(여자)처럼 분류 코드가
  // 단면을 넘어 충돌하므로, 어느 단면인지를 매트릭스 조회 키에 반드시 실어야 한다.
  const rows = breakdownMatrix(ctx.series, segment.categories, ctx.state.period, { sort, breakdown: current });

  const note = current === 'industry' ? '' : `<p class="note note--est">${esc(EST_NOTE)}</p>`;
  const head = `<thead><tr><th scope="col">${esc(segment.name_ko)}</th>${
    SOURCE_ORDER.map(s => `<th scope="col"><a href="${esc(
      (ctx.sources.find(m => m.code === s) || {}).board_url || '#')}" rel="noopener">${esc(
      (ctx.sources.find(m => m.code === s) || {}).name_ko || s)}</a></th>`).join('')
  }</tr></thead>`;

  const body = rows.map(row => `
    <tr class="row" data-code="${esc(row.code)}">
      <th scope="row">${esc(row.name_ko)}</th>
      ${SOURCE_ORDER.map(s => cell(row.cells[s].state, row.cells[s].yoy)).join('')}
    </tr>
    ${ctx.state.category === row.code ? expanded(ctx, current, row) : ''}`).join('');

  el.innerHTML = tabs(segments, current) + note + `
    <div class="sortbar">
      <button type="button" class="sortbtn${sort === 'delta' ? ' is-on' : ''}" data-sort="delta">증감순</button>
      <button type="button" class="sortbtn${sort === 'code' ? ' is-on' : ''}" data-sort="code">분류순</button>
    </div>
    <table class="matrix">${head}<tbody>${body}</tbody></table>
    <p class="legend">미제공 = 그 출처가 공표하지 않는 분류 · 미발표 = 아직 그 달을 내지 않음 · 증감없음 = 전년동월대비를 낼 수 없음</p>`;

  el.querySelectorAll('.sortbtn').forEach(btn => btn.addEventListener('click', () => {
    ctx.state.sort = btn.dataset.sort;
    ctx.rerender();
  }));
  el.querySelectorAll('.row').forEach(tr => tr.addEventListener('click', () => {
    const code = tr.dataset.code;
    location.hash = ctx.state.category === code ? `#/b/${current}` : `#/b/${current}/${encodeURIComponent(code)}`;
  }));
}

function expanded(ctx, breakdown, row) {
  const timeline = categoryTimeline(ctx.series, { breakdown, category: row.code, months: 24 });
  const lines = SOURCE_ORDER.map(s => {
    const name = (ctx.sources.find(m => m.code === s) || {}).name_ko || s;
    const dot = `<span class="dot" style="background:${esc(SOURCE_COLORS[s])}"></span>`;
    const points = timeline[s];
    // 점이 없다고 행을 지우지 않는다. 사업체노동력조사가 농림어업을 잡지 않는다는
    // 사실 자체가 정보다(상위 스펙 7.6) — 시트의 막대는 이미 이걸 지키는데
    // 이 화면만 어겼다. 왜 비었는지는 매트릭스 칸이 이미 들고 있는 cellState
    // 판정을 그대로 쓴다. 여기서 세 번째 판정을 만들지 않는다.
    if (!points.length) {
      return `<li>${dot}${esc(name)} · ${esc(emptyLabel(row.cells[s].state))}</li>`;
    }
    const last = points[points.length - 1];
    const label = last.yoy === null ? emptyLabel('noDelta') : fmtDelta(last.yoy);
    return `<li>${dot}
      ${esc(name)} · ${esc(monthLabel(last.period))} ${esc(label)}</li>`;
  }).join('');
  return `<tr class="expand"><td colspan="4"><ul class="expand__list">${lines}</ul></td></tr>`;
}

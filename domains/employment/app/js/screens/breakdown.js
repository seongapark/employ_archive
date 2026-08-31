import { segmentsOf, breakdownMatrix, categoryTimeline, fmtDelta, monthLabel, esc, SOURCE_ORDER, SOURCE_COLORS } from '../data.js';

const EMPTY_LABEL = { notProvided: '―', unpublished: '미발표', noDelta: '증감없음' };

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
    return `<td class="num ${yoy >= 0 ? 'is-up' : 'is-down'}">${esc(fmtDelta(yoy))}</td>`;
  }
  return `<td class="cell--empty">${esc(EMPTY_LABEL[state])}</td>`;
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
    <p class="legend">― 미제공 · 미발표 = 아직 그 달을 내지 않음 · 증감없음 = 전년동월대비를 낼 수 없음</p>`;

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
    const points = timeline[s];
    if (!points.length) return '';
    const last = points[points.length - 1];
    const name = (ctx.sources.find(m => m.code === s) || {}).name_ko || s;
    return `<li><span class="dot" style="background:${esc(SOURCE_COLORS[s])}"></span>
      ${esc(name)} · ${esc(monthLabel(last.period))} ${esc(last.yoy === null ? '증감없음' : fmtDelta(last.yoy))}</li>`;
  }).join('');
  return `<tr class="expand"><td colspan="4"><ul class="expand__list">${lines}</ul></td></tr>`;
}

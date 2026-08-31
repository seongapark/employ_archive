import { switcherHtml, bindSwitcher } from '../switcher.js';
import {
  segmentsOf, breakdownMatrix, fmtLevel, categoryTimeline, fmtDelta, deltaTone, monthLabel,
  EMPTY_LABEL, emptyLabel, esc, shortOf, totalRow, SOURCE_ORDER, SOURCE_COLORS,
} from '../data.js';

// 사업체노동력조사가 성·연령에서 통째로 비는 이유를 화면이 말한다.
// 열을 지우면 "안 잡는다"는 사실 자체가 사라진다.
const EST_NOTE = '사업체노동력조사는 성·연령별 종사자수를 공표하지 않습니다.';

// 두 출처가 같은 구간을 다르게 부른다. 연령만 적는다 — 남자/남성은 누구도
// 다르게 읽지 않지만, 15∼29세와 29세이하는 서로 다른 구간처럼 보인다.
const AGE_NOTE = '경활은 15∼29세, 고용행정은 29세이하로 쓴다 · 이 앱은 29세 이하로 통일';

function tabs(segments, current) {
  return `<div class="btabs">${segments.map(s =>
    `<a class="btab${s.breakdown === current ? ' btab--active' : ''}" href="#/b/${s.breakdown}">${esc(s.name_ko)}</a>`
  ).join('')}</div>`;
}

// 칸은 증감만 쓴다. 좁은 화면에서 한 칸에 두 숫자를 넣으면 21행이 다시 길어진다 —
// 수준은 행을 탭했을 때 펼침에서 보여준다.
function cell({ state, yoy }) {
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
  // 속성을 넘어 충돌하므로, 어느 속성인지를 매트릭스 조회 키에 반드시 실어야 한다.
  const rows = breakdownMatrix(ctx.series, segment.categories, ctx.state.period, { sort, breakdown: current });

  const note = current === 'industry' ? '' : `<p class="note note--est">${esc(EST_NOTE)}</p>`;
  // 열 머리는 출처 약칭(경활·사업체·행정통계)이다. 정식명을 쓰면 세 번째 열이
  // 휴대폰 화면 밖으로 잘려 나간다. 정식명은 title 로 남겨 길게 눌렀을 때 뜨고,
  // 출처비교 화면이 전체를 나열한다.
  const head = `<thead><tr><th scope="col">${esc(segment.name_ko)}</th>${
    SOURCE_ORDER.map(s => {
      const meta = ctx.sources.find(m => m.code === s) || {};
      return `<th scope="col"><a href="${esc(meta.board_url || '#')}" rel="noopener"
        title="${esc(meta.name_ko || s)}">${esc(shortOf(meta) || s)}</a></th>`;
    }).join('')
  }</tr></thead>`;

  // 전체 증감은 정렬과 무관하게 항상 첫 줄이다. 분류 행처럼 펼쳐지지 않는다 —
  // 시계열은 이미 시트가 전체 기준으로 보여준다.
  const total = totalRow(ctx.series, ctx.state.period);
  const totalHtml = `
    <tr class="matrix__total">
      <th scope="row">${esc(total.short_ko)}</th>
      ${SOURCE_ORDER.map(s => cell(total.cells[s])).join('')}
    </tr>`;

  const body = rows.map(row => `
    <tr class="row" data-code="${esc(row.code)}">
      <th scope="row" title="${esc(row.name_ko)}">${esc(shortOf(row))}</th>
      ${SOURCE_ORDER.map(s => cell(row.cells[s])).join('')}
    </tr>
    ${ctx.state.category === row.code ? expanded(ctx, current, row) : ''}`).join('');

  el.innerHTML = switcherHtml(ctx) + tabs(segments, current) + note + `
    <div class="sortbar">
      <button type="button" class="sortbtn${sort === 'delta' ? ' is-on' : ''}" data-sort="delta">증감순</button>
      <button type="button" class="sortbtn${sort === 'code' ? ' is-on' : ''}" data-sort="code">분류순</button>
    </div>
    <table class="matrix">${head}<tbody>${totalHtml}${body}</tbody></table>
    <ul class="legend">
      <li>미제공 = 그 출처가 공표하지 않는 분류</li>
      <li>미발표 = 아직 그 달을 내지 않음</li>
      <li>증감없음 = 전년동월대비를 낼 수 없음</li>
      ${current === 'age' ? `<li>${esc(AGE_NOTE)}</li>` : ''}
    </ul>`;

  bindSwitcher(el, ctx);

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
    const name = shortOf(ctx.sources.find(m => m.code === s)) || s;
    const dot = `<span class="dot" style="background:${esc(SOURCE_COLORS[s])}"></span>`;
    const points = timeline[s];
    // 점이 없다고 행을 지우지 않는다. 사업체노동력조사가 농림어업을 잡지 않는다는
    // 사실 자체가 정보다(상위 스펙 7.6) — 시트의 막대는 이미 이걸 지키는데
    // 이 화면만 어겼다. 왜 비었는지는 매트릭스 칸이 이미 들고 있는 cellState
    // 판정을 그대로 쓴다. 여기서 세 번째 판정을 만들지 않는다.
    // 펼침은 그 달의 수준과 증감을 함께 보여준다. 매트릭스는 증감만 싣고,
    // "그래서 규모가 얼마인데?" 는 여기서 답한다.
    const here = row.cells[s];
    const level = here.value === null || here.value === undefined
      ? '' : ` <span class="expand__level num">${esc(fmtLevel(here.value))}</span>`;
    if (!points.length) {
      return `<li>${dot}${esc(name)} · ${esc(emptyLabel(here.state))}${level}</li>`;
    }
    const last = points[points.length - 1];
    const label = here.state === 'noDelta' ? emptyLabel('noDelta') : fmtDelta(here.yoy);
    return `<li>${dot}${esc(name)} · ${esc(label)}${level}</li>`;
  }).join('');
  // 약칭만으로는 뜻이 흐린 분류가 있다(가구내고용·국제외국·수도·하수·폐기업).
  // 펼쳤을 때 정식명을 한 줄 얹어 표의 좁은 머리와 원문 이름을 잇는다.
  const full = row.short_ko && row.short_ko !== row.name_ko
    ? `<p class="expand__full">${esc(row.name_ko)}</p>` : '';
  return `<tr class="expand"><td colspan="4">${full}<ul class="expand__list">${lines}</ul></td></tr>`;
}

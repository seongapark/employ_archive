import { sheetData, segmentsOf, monthLabel, esc } from './data.js';
import { barsSvg, timelineSvg, sheetTable } from './chart.js';

const KEY = 'employment.sheet';
const TABLE_KEY = 'employment.sheet.table';

function read(key) {
  try { return localStorage.getItem(key); } catch { return null; }
}
function write(key, value) {
  try { localStorage.setItem(key, value); } catch { /* 사파리 프라이빗 등 */ }
}

export function mountSheet(sheetEl, handleEl, labelEl, ctx) {
  let open = read(KEY) === '1';
  let asTable = read(TABLE_KEY) === '1';

  function cut() {
    const segments = segmentsOf(ctx.industries, ctx.segments);
    const breakdown = ctx.state.category ? ctx.state.breakdown : null;
    const segment = segments.find(s => s.breakdown === breakdown);
    const category = ctx.state.category || null;
    const label = category && segment
      ? (segment.categories.find(c => c.code === category) || {}).name_ko || category
      : '전체';
    return { breakdown, category, categories: segment ? segment.categories : null, label };
  }

  function refresh() {
    const { breakdown, category, categories, label } = cut();
    const data = sheetData(ctx.series, { period: ctx.state.period, breakdown, category, categories });
    const names = Object.fromEntries(ctx.sources.map(s => [s.code, s.name_ko]));

    labelEl.textContent = `증감 비교 · ${monthLabel(ctx.state.period)} · ${label}`;
    handleEl.setAttribute('aria-expanded', String(open));
    sheetEl.hidden = !open;
    if (!open) return;

    sheetEl.innerHTML = `
      <div class="sheet__head">
        <span>증감 비교 · ${esc(monthLabel(ctx.state.period))} · ${esc(label)}</span>
        <button type="button" class="sheet__toggle" id="sheetTableToggle">${asTable ? '그래프로 보기' : '표로 보기'}</button>
      </div>
      ${asTable
        ? sheetTable(data.snapshot, data.timeline, { sourceNames: names })
        : barsSvg(data.snapshot, { width: 320, sourceNames: names }) +
          timelineSvg(data.timeline, { width: 320, height: 160, selected: ctx.state.period })}
      <ul class="sheet__legend">${
        data.snapshot.map(s => `<li><span class="dot" data-source="${esc(s.source)}"></span>${esc(names[s.source] || s.source)}</li>`).join('')
      }</ul>`;

    sheetEl.querySelector('#sheetTableToggle').addEventListener('click', () => {
      asTable = !asTable;
      write(TABLE_KEY, asTable ? '1' : '0');
      refresh();
    });
  }

  handleEl.addEventListener('click', () => {
    open = !open;
    write(KEY, open ? '1' : '0');
    refresh();
  });

  refresh();
  return { refresh };
}

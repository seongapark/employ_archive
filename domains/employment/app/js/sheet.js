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
    const found = category && segment ? segment.categories.find(c => c.code === category) : null;
    // 낡은 해시(북마크·뒤로가기)가 현재 분류에 없는 코드를 가리키면 전체 컷으로 떨어진다.
    // 원문 코드를 라벨로 흘리거나(예: "· C") 존재하지 않는 조합을 sheetData 에 넘겨
    // 세 행이 전부 unpublished 로 뜨는 무의미한 화면을 만들지 않는다.
    if (category && !found) {
      return { breakdown: null, category: null, categories: null, label: '전체' };
    }
    const label = found ? (found.name_ko || category) : '전체';
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

  // 배경 탭으로 닫기. 문서 전체에 한 번만 붙인다 — refresh() 안에 두면 refresh 가
  // 호출될 때마다 리스너가 쌓인다. 핸들을 여는 그 클릭이 곧바로 다시 닫히지 않는
  // 이유: 클릭은 handleEl 에서 시작해 버블링으로 document 까지 올라오는데, 위
  // handleEl 리스너가 target 단계에서 먼저 실행되어 open 을 true 로 뒤집고,
  // 이 리스너가 버블 단계에서 나중에 실행될 때는 e.target 이 이미 handleEl 이므로
  // `handleEl.contains(e.target)` 가지드에 걸려 그대로 반환한다.
  document.addEventListener('click', (e) => {
    if (!open) return;
    if (sheetEl.contains(e.target) || handleEl.contains(e.target)) return;
    open = false;
    write(KEY, '0');
    refresh();
  });

  refresh();
  return { refresh };
}

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

export function mountSheet(sheetEl, handleEl, labelEl, scrimEl, ctx) {
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
    scrimEl.hidden = !open;
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

  // 배경 탭으로 닫기(상위 스펙 7.6). "배경"은 스크림 하나다 — 문서 전체가 아니다.
  //
  // WHY 스크림인가: 예전에는 document 에 리스너를 걸고 sheetEl/handleEl 바깥을
  // 누르면 닫았다. 시트가 문서 흐름 안의 정적 블록이었기 때문에 "바깥"이 곧
  // 페이지 전부였고, 세그먼트·연월 셀렉트·정렬 버튼·분류 행을 누르는 것만으로
  // 시트가 닫히며 localStorage 에 '0' 이 박혔다. 특히 여자 행을 눌러 시트 기준을
  // 바꾸려는 이 앱의 핵심 동작이 시트를 닫아 버렸다.
  //
  // 스크림은 열려 있을 때만 존재하고 시트(z 25)·핸들(z 30) 보다 아래(z 20)에
  // 있으므로, 시트 안이나 핸들을 누른 클릭은 애초에 이 리스너에 도달하지 않는다.
  // 가드도, 이벤트 단계 조작도 필요 없다 — 닫히는 경우가 기하학으로 한정된다.
  // 리스너는 여기서 한 번만 붙인다. refresh() 안에 두면 호출마다 쌓인다.
  scrimEl.addEventListener('click', () => {
    if (!open) return;
    open = false;
    write(KEY, '0');
    refresh();
  });

  refresh();
  return { refresh };
}

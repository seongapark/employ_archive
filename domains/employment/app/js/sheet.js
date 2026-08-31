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
  // 호출될 때마다 리스너가 쌓인다.
  //
  // capture 단계에서 잡는 이유(WHY): 시트 안의 컨트롤(#sheetTableToggle 등)은
  // 클릭 시 refresh() 를 호출해 sheetEl.innerHTML 을 통째로 다시 쓴다. 이게
  // 버블 단계가 오기 "전에" 일어나면, 클릭됐던 노드는 이미 문서에서 떨어져
  // 나간 뒤라 e.target 이 고아 노드가 되고 `sheetEl.contains(e.target)` 는
  // false 를 돌려준다 — 가드가 뚫려서 시트 안을 눌렀을 뿐인데 시트가 닫히고
  // localStorage 에까지 '0' 이 저장된다. capture 단계는 target 단계보다 먼저
  // 실행되므로 innerHTML 이 아직 재작성되기 전에 e.target 이 살아있는 채로
  // 이 가드를 통과한다. 나중에 시트 안에 새 컨트롤을 추가해도 같은 클래스의
  // 버그를 자동으로 피한다. 이걸 "단순화"한다고 버블 단계로 되돌리지 말 것 —
  // 위 문단이 그 이유다.
  //
  // 세 경로의 순서를 여기서 다시 확인한다:
  // 1) 여는 클릭(핸들): capture 리스너가 handleEl 의 클릭 핸들러보다 먼저
  //    실행된다. 이 시점엔 아직 open=false 이므로 `if (!open) return;` 에
  //    걸려 그대로 빠진다 — 시트는 정상적으로 열린다.
  // 2) 닫는 클릭(핸들 재탭): open=true 인 상태에서 capture 리스너가 먼저
  //    돌지만 e.target(핸들 또는 그 안의 <span>)이 `handleEl.contains(e.target)`
  //    를 만족해 되돌아간다. 이어서 target 단계의 handleEl 리스너가 실행되어
  //    직접 닫는다.
  // 3) 시트 안 클릭(표로 보기 등): capture 리스너가 먼저 돌 때 아직
  //    sheetEl.innerHTML 이 재작성되지 않았으므로 e.target 은 여전히
  //    sheetEl 의 자손이고 `sheetEl.contains(e.target)` 가 true 라 되돌아간다.
  //    그 뒤 target 단계의 토글 핸들러가 실행되며 refresh() 가 innerHTML 을
  //    다시 쓴다 — 시트는 열린 채로 남는다.
  document.addEventListener('click', (e) => {
    if (!open) return;
    if (sheetEl.contains(e.target) || handleEl.contains(e.target)) return;
    open = false;
    write(KEY, '0');
    refresh();
  }, true);

  refresh();
  return { refresh };
}

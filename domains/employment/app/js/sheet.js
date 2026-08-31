import { sheetData, segmentsOf, monthLabel, esc, shortOf } from './data.js';
import { barsSvg, timelineSvg, sheetTable, timelinePeriods, periodAtRatio } from './chart.js';

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
  // 그래프의 기준월. 위쪽 연·월 스위처와 **완전히 분리**된다 — 점선을 끌어도
  // 총괄 카드와 매트릭스는 그대로고, 스위처를 바꿔도 이 선은 움직이지 않는다.
  // 시트는 시계열을 훑는 도구이고 화면은 한 달을 보는 도구라, 둘을 묶으면
  // 훑는 동안 화면이 계속 흔들린다. 처음 값만 화면의 월에서 가져온다.
  let scrub = ctx.state.period;
  let dragging = false;

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
    const label = found ? (shortOf(found) || category) : '전체';
    return { breakdown, category, categories: segment ? segment.categories : null, label };
  }

  // 시트 안은 두 겹이다. 골격(머리·표 토글·그림 자리·범례)은 refresh() 가 한 번
  // 만들고, 드래그로 달이 바뀔 때는 paint() 가 그림과 월 글자만 갈아 끼운다.
  // 골격까지 다시 그리면 끌고 있던 SVG 가 사라져 손가락이 허공을 짚는다.
  function paint() {
    const { breakdown, category, categories, label } = cut();
    let data = sheetData(ctx.series, { period: scrub, breakdown, category, categories });
    // 속성을 바꾸면 기간 목록이 달라진다. scrub 이 그 밖으로 나가면 세 행이 모두
    // 미발표로 뜨는 빈 그래프가 되므로 최신월로 당긴다.
    const periods = timelinePeriods(data.timeline);
    if (periods.length && !periods.includes(scrub)) {
      scrub = periods[periods.length - 1];
      data = sheetData(ctx.series, { period: scrub, breakdown, category, categories });
    }
    const names = Object.fromEntries(ctx.sources.map(s => [s.code, shortOf(s)]));

    const monthEl = sheetEl.querySelector('.sheet__month');
    if (monthEl) monthEl.textContent = monthLabel(scrub);
    const cutEl = sheetEl.querySelector('.sheet__cut');
    if (cutEl) cutEl.textContent = label;

    const body = sheetEl.querySelector('.sheet__body');
    if (body) {
      body.innerHTML = asTable
        ? sheetTable(data.snapshot, data.timeline, { sourceNames: names })
        : barsSvg(data.snapshot, { width: 320, sourceNames: names });
    }
    const line = sheetEl.querySelector('.sheet__line');
    if (line) {
      line.innerHTML = asTable
        ? ''
        : timelineSvg(data.timeline, { width: 320, height: 160, selected: scrub });
    }
    return periods;
  }

  function refresh() {
    handleEl.setAttribute('aria-expanded', String(open));
    sheetEl.hidden = !open;
    scrimEl.hidden = !open;
    // 핸들은 짧게 — 월은 시트 안에서 드래그로 바뀌므로 닫힌 상태에서 월을 적으면
    // 열자마자 다른 달을 가리키는 일이 생긴다.
    labelEl.textContent = '증감비교(그래프)';
    if (!open) return;

    sheetEl.innerHTML = `
      <div class="sheet__head">
        <span>증감 비교 · <b class="sheet__month"></b> · <span class="sheet__cut"></span></span>
        <button type="button" class="sheet__toggle" id="sheetTableToggle">${asTable ? '그래프로 보기' : '표로 보기'}</button>
      </div>
      <div class="sheet__body"></div>
      <div class="sheet__line"></div>
      <p class="sheet__hint">${asTable ? '' : '점선을 끌면 기준월이 바뀝니다.'}</p>
      <ul class="sheet__legend">${
        ctx.sources.map(s => `<li><span class="dot" data-source="${esc(s.code)}"></span>${esc(shortOf(s))}</li>`).join('')
      }</ul>`;

    const periods = paint();

    sheetEl.querySelector('#sheetTableToggle').addEventListener('click', () => {
      asTable = !asTable;
      write(TABLE_KEY, asTable ? '1' : '0');
      refresh();
    });

    bindScrub(sheetEl.querySelector('.sheet__line'), periods);
  }

  // 시계열을 끌어 기준월을 옮긴다. 선 자체를 잡게 하면 1px 을 조준해야 하므로
  // 그래프 어디를 눌러도 가장 가까운 달로 붙는다.
  //
  // 리스너는 SVG 가 아니라 그것을 감싼 .sheet__line 에 건다. paint() 가 그 안의
  // SVG 를 갈아 끼우기 때문에 SVG 에 걸면 첫 이동에서 리스너와 포인터 캡처가
  // 함께 사라진다. 감싼 칸은 그대로 남으므로 끌기가 끊기지 않는다.
  function bindScrub(box, periods) {
    if (!box || periods.length < 2 || asTable) return;

    const move = event => {
      const rect = box.getBoundingClientRect();
      if (!rect.width) return;
      const next = periodAtRatio(periods, (event.clientX - rect.left) / rect.width);
      if (!next || next === scrub) return;
      scrub = next;
      paint();
    };

    // 포인터 캡처는 실패해도 끌기를 막지 않는다. setPointerCapture 는 포인터가
    // 이미 놓였거나 id 가 유효하지 않으면 NotFoundError 를 던지는데, 그대로 두면
    // 예외가 pointerdown 핸들러를 끊어 dragging 이 켜지지도 않는다 — 캡처는
    // 손가락이 그래프 밖으로 나가도 따라오게 하는 편의일 뿐이고, 없어도
    // 그래프 안에서의 끌기는 그대로 된다.
    const capture = (fn, id) => { try { fn(id); } catch { /* 캡처 없이 진행 */ } };

    box.addEventListener('pointerdown', event => {
      event.preventDefault();          // 세로 스크롤이 끌기를 가로채지 않게
      capture(box.setPointerCapture?.bind(box), event.pointerId);
      dragging = true;
      move(event);
    });
    box.addEventListener('pointermove', event => {
      if (dragging) move(event);
    });
    for (const done of ['pointerup', 'pointercancel']) {
      box.addEventListener(done, event => {
        dragging = false;
        capture(box.releasePointerCapture?.bind(box), event.pointerId);
      });
    }
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

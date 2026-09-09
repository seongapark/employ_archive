// 홈 — 검색창이 맨 위에 상주하고, 그 아래가 기본 상태에서 최신발간 타임라인이다.
// 검색어를 치면 타임라인 자리가 결과로 바뀌고, 지우면 돌아온다.
import {
  esc, groupTimeline, filterReports, monthLabel, yearsOf,
} from '../data.js';
import { searchReports, sortByDate } from '../search.js';
import { reportRow, foldRow, chip, empty } from '../ui.js';

const ORGS = [
  ['kli', 'KLI'], ['keis', 'KEIS'], ['kdi', 'KDI'], ['kiet', 'KIET'],
];

// 순수 함수. 상태와 데이터를 받아 무엇을 그릴지만 정한다.
export function homeRows(state, ctx) {
  const pool = filterReports(ctx.reports, {
    orgs: state.orgs || [], years: state.years || [],
  });
  const q = (state.q || '').trim();
  if (!q) {
    return {
      mode: 'timeline',
      groups: groupTimeline(pool, ctx.boards, { expanded: state.expanded || new Set() }),
    };
  }
  let hits = searchReports(q, pool, ctx.abstracts);
  if (state.sort === 'date') hits = sortByDate(hits);
  return { mode: 'search', hits };
}

export function render(el, ctx) {
  const state = ctx.state;
  const rows = homeRows(state, ctx);
  const years = yearsOf(ctx.reports);

  const head = `
    <div class="searchbar">
      <div class="searchbar__box">
        <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="7"></circle><path d="M20 20l-3.5-3.5"></path></svg>
        <input id="q" type="text" placeholder="제목·저자·초록·목차에서 찾기"
               value="${esc(state.q || '')}" autocomplete="off" enterkeyhint="search">
        ${state.q ? '<button class="searchbar__clear" type="button" id="clearQ" aria-label="지우기">×</button>' : ''}
      </div>
    </div>
    <div class="chips">
      ${ORGS.map(([code, label]) => chip(label, (state.orgs || []).includes(code), `data-org="${code}"`)).join('')}
      ${years.slice(0, 8).map((y) => chip(`${y}`, (state.years || []).includes(y), `data-year="${y}"`)).join('')}
    </div>`;

  let body;
  if (rows.mode === 'search') {
    const count = rows.hits.length;
    body = `
      <div class="chips">
        ${chip('관련도순', state.sort !== 'date', 'data-sort="score"')}
        ${chip('최신순', state.sort === 'date', 'data-sort="date"')}
        <span class="chip" style="border:0;background:transparent;cursor:default">${count}건</span>
      </div>
      <div class="list">
        ${count ? rows.hits.map((h) => reportRow(h.report, {
          snippet: h.hit.snippet, query: state.q,
        })).join('') : ''}
      </div>`;
    if (!count) {
      body += empty(`‘${esc(state.q)}’ 에 걸리는 보고서가 없습니다.<br>기관·연도 칩을 풀어 보세요.`);
    }
  } else if (!rows.groups.length) {
    body = empty(ctx.reports.length
      ? '고른 조건에 맞는 보고서가 없습니다.'
      : '아직 수집된 보고서가 없습니다.');
  } else {
    body = rows.groups.map((g) => `
      <div class="month">${esc(monthLabel(g.month))}</div>
      <div class="list">
        ${g.rows.map((row) => (row.kind === 'collapsed'
          ? foldRow(row)
          : reportRow(row.report, { inGroup: row.inGroup }))).join('')}
      </div>`).join('');
  }

  el.innerHTML = head + body;
  wire(el, ctx);
}

function wire(el, ctx) {
  const state = ctx.state;
  const input = el.querySelector('#q');
  if (input) {
    // 초록은 검색창에 포커스가 가는 순간 미리 받는다. 타이핑을 시작할 때는
    // 이미 와 있어서 결과가 두 단계로 늘어나 보이지 않는다.
    input.addEventListener('focus', () => ctx.prefetchAbstracts(), { once: true });
    input.addEventListener('input', () => {
      state.q = input.value;
      ctx.rerender({ keepFocus: true });
    });
  }
  const clear = el.querySelector('#clearQ');
  if (clear) {
    clear.addEventListener('click', () => { state.q = ''; ctx.rerender(); });
  }
  el.querySelectorAll('[data-org]').forEach((b) => {
    b.addEventListener('click', () => {
      state.orgs = toggle(state.orgs || [], b.dataset.org);
      ctx.rerender();
    });
  });
  el.querySelectorAll('[data-year]').forEach((b) => {
    b.addEventListener('click', () => {
      state.years = toggle(state.years || [], Number(b.dataset.year));
      ctx.rerender();
    });
  });
  el.querySelectorAll('[data-sort]').forEach((b) => {
    b.addEventListener('click', () => { state.sort = b.dataset.sort; ctx.rerender(); });
  });
  el.querySelectorAll('[data-fold]').forEach((b) => {
    b.addEventListener('click', () => {
      const id = b.dataset.fold;
      state.expanded = state.expanded || new Set();
      if (state.expanded.has(id)) state.expanded.delete(id);
      else state.expanded.add(id);
      ctx.rerender({ keepScroll: true });
    });
  });
}

function toggle(list, value) {
  return list.includes(value) ? list.filter((x) => x !== value) : [...list, value];
}

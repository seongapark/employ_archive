// 홈 — 검색창이 맨 위에 상주하고, 그 아래가 기본 상태에서 최신발간 타임라인이다.
// 검색어를 치면 타임라인 자리가 결과로 바뀌고, 지우면 돌아온다.
//
// **머리(검색창·칩)와 본문(목록)을 나눠 그린다.** 한 글자 칠 때마다 화면 전체를
// 다시 그리면 입력창 DOM 이 교체되는데, 그러면 한글 조합(초성+중성+종성)이 매
// 글자마다 끊겨 '사무직' 이 'ㅅㅏㅁㅜㅈㅣㄱ' 으로 들어간다. 영문은 조합이 없어
// 드러나지 않는다. 머리는 한 번만 그리고 본문만 갈아 끼운다 — 이 경계를 없애면
// 그 버그가 그대로 돌아온다.
import {
  esc, groupTimeline, filterReports, monthLabel, yearsOf,
} from '../data.js';
import { searchReports, sortByDate } from '../search.js';
import { reportRow, foldRow, chip, empty } from '../ui.js';

const ORGS = [
  ['kli', 'KLI'], ['keis', 'KEIS'], ['kdi', 'KDI'], ['kiet', 'KIET'], ['bok', 'BOK'],
];

// 순수 함수. 상태와 데이터를 받아 무엇을 그릴지만 정한다.
export function homeRows(state, ctx) {
  const pool = filterReports(ctx.reports, {
    orgs: state.orgs || [], years: state.years || [],
  });
  const q = (state.q || '').trim();
  if (!q) {
    // 타임라인 행에만 추천 배지를 붙인다 — 검색 결과는 관련도가 이미 주인공이다.
    const picks = ctx.picks || {};
    const marked = pool.map((r) => (picks[r.id] && picks[r.id].pick ? { ...r, picked: true } : r));
    return {
      mode: 'timeline',
      groups: groupTimeline(marked, ctx.boards, { expanded: state.expanded || new Set() }),
    };
  }
  let hits = searchReports(q, pool, ctx.abstracts);
  if (state.sort === 'date') hits = sortByDate(hits);
  return { mode: 'search', hits };
}

const HOME_PICKS = 6;
const PER_ORG = 2;   // BOK 이슈노트가 여섯 줄을 통째로 채우는 걸 막는다

// 발행일 내림차순 6건, 한 기관 최대 2건. 검색창 아래 '읽을 만한 보고서' 에 쓴다.
export function topPicks(reports, picks) {
  const picked = (reports || [])
    .filter((r) => (picks || {})[r.id] && picks[r.id].pick)
    .sort((a, b) => (a.published < b.published ? 1 : -1));
  const out = [];
  const seen = new Map();
  for (const r of picked) {
    const n = seen.get(r.org) || 0;
    if (n >= PER_ORG) continue;
    seen.set(r.org, n + 1);
    out.push({ ...r, why: picks[r.id].why, axis: picks[r.id].axis });
    if (out.length >= HOME_PICKS) break;
  }
  return out;
}

// 머리는 검색어에 기대지 않는다. 이 함수가 state.q 를 읽기 시작하면 머리를 다시
// 그려야 하고, 그 순간 입력창이 교체돼 한글 조합이 깨진다.
export function headHtml(state, ctx) {
  const years = yearsOf(ctx.reports);
  return `
    <div class="searchbar">
      <div class="searchbar__box">
        <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="7"></circle><path d="M20 20l-3.5-3.5"></path></svg>
        <input id="q" type="text" placeholder="제목·저자·초록·목차에서 찾기"
               autocomplete="off" enterkeyhint="search">
        <button class="searchbar__clear" type="button" id="clearQ" aria-label="지우기" hidden>×</button>
      </div>
    </div>
    <div class="chips" id="filterChips">
      ${ORGS.map(([code, label]) => chip(label, (state.orgs || []).includes(code), `data-org="${code}"`)).join('')}
      ${years.slice(0, 8).map((y) => chip(`${y}`, (state.years || []).includes(y), `data-year="${y}"`)).join('')}
    </div>`;
}

export function bodyHtml(state, ctx) {
  const rows = homeRows(state, ctx);
  if (rows.mode === 'search') {
    const count = rows.hits.length;
    const sortChips = `
      <div class="chips">
        ${chip('관련도순', state.sort !== 'date', 'data-sort="score"')}
        ${chip('최신순', state.sort === 'date', 'data-sort="date"')}
        <span class="chip" style="border:0;background:transparent;cursor:default">${count}건</span>
      </div>`;
    if (!count) {
      return sortChips + empty(
        `‘${esc(state.q)}’ 에 걸리는 보고서가 없습니다.<br>기관·연도 칩을 풀어 보세요.`);
    }
    return sortChips + `<div class="list">${rows.hits.map((h) => reportRow(h.report, {
      snippet: h.hit.snippet, query: state.q,
    })).join('')}</div>`;
  }
  // 검색 중에는 그리지 않는다 — 여기 도달했다면 이미 timeline 모드다.
  const picks = topPicks(ctx.reports, ctx.picks);
  const picksHtml = picks.length ? `
    <div class="section-title">
      읽을 만한 보고서
      <a class="more" href="#/picks">더보기 ›</a>
    </div>
    <div class="list">
      ${picks.map((r) => `${reportRow(r)}<div class="why">${esc(r.why)}</div>`).join('')}
    </div>` : '';
  if (!rows.groups.length) {
    return picksHtml + empty(ctx.reports.length
      ? '고른 조건에 맞는 보고서가 없습니다.'
      : '아직 수집된 보고서가 없습니다.');
  }
  return picksHtml + rows.groups.map((g) => `
    <div class="month">${esc(monthLabel(g.month))}</div>
    <div class="list">
      ${g.rows.map((row) => (row.kind === 'collapsed'
        ? foldRow(row)
        : reportRow(row.report, { inGroup: row.inGroup }))).join('')}
    </div>`).join('');
}

export function render(el, ctx) {
  const state = ctx.state;
  el.innerHTML = '<div id="homeHead"></div><div id="homeBody"></div>';
  const headEl = el.querySelector('#homeHead');
  const bodyEl = el.querySelector('#homeBody');

  headEl.innerHTML = headHtml(state, ctx);
  const input = headEl.querySelector('#q');
  const clear = headEl.querySelector('#clearQ');
  input.value = state.q || '';
  clear.hidden = !state.q;

  const drawBody = () => {
    bodyEl.innerHTML = bodyHtml(state, ctx);
    wireBody(bodyEl, ctx, drawBody);
  };
  // 초록이 나중에 도착하면 본문만 다시 그린다 — 입력창을 건드리지 않는다.
  ctx.refreshBody = drawBody;

  // 조합 중에도 input 이벤트는 온다. 입력창을 그대로 두므로 조합은 안 끊기고
  // 결과만 따라 바뀐다.
  // 포커스에서 미리 받는 게 정상 경로다. 다만 그 이벤트를 놓치면(이미 포커스된
  // 채로 들어오는 경우 등) 검색이 제목만 훑는 상태로 조용히 주저앉는다 —
  // 입력에서도 한 번 더 부른다. prefetchAbstracts 는 두 번 불러도 한 번만 받는다.
  input.addEventListener('focus', () => ctx.prefetchAbstracts(), { once: true });
  input.addEventListener('input', () => {
    ctx.prefetchAbstracts();
    state.q = input.value;
    clear.hidden = !state.q;
    drawBody();
  });
  clear.addEventListener('click', () => {
    state.q = '';
    input.value = '';
    clear.hidden = true;
    input.focus();
    drawBody();
  });

  headEl.querySelectorAll('[data-org]').forEach((b) => {
    b.addEventListener('click', () => {
      state.orgs = toggle(state.orgs || [], b.dataset.org);
      b.classList.toggle('chip--active');     // 머리를 다시 그리지 않는다
      drawBody();
    });
  });
  headEl.querySelectorAll('[data-year]').forEach((b) => {
    b.addEventListener('click', () => {
      state.years = toggle(state.years || [], Number(b.dataset.year));
      b.classList.toggle('chip--active');
      drawBody();
    });
  });

  drawBody();
}

function wireBody(bodyEl, ctx, drawBody) {
  const state = ctx.state;
  bodyEl.querySelectorAll('[data-sort]').forEach((b) => {
    b.addEventListener('click', () => { state.sort = b.dataset.sort; drawBody(); });
  });
  bodyEl.querySelectorAll('[data-fold]').forEach((b) => {
    b.addEventListener('click', () => {
      const id = b.dataset.fold;
      state.expanded = state.expanded || new Set();
      if (state.expanded.has(id)) state.expanded.delete(id);
      else state.expanded.add(id);
      drawBody();          // 본문만 갈아서 보고 있던 자리가 유지된다
    });
  });
}

function toggle(list, value) {
  return list.includes(value) ? list.filter((x) => x !== value) : [...list, value];
}

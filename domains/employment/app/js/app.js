import { render as overview } from './screens/overview.js';
import { render as breakdown } from './screens/breakdown.js';
import { render as sources } from './screens/sources.js';
import { render as release } from './screens/release.js';
import { mountSheet } from './sheet.js';
import { monthOptions } from './data.js';
import { loadJson } from '../core/shell.js';
import { parseRoute } from './route.js';

const screens = { overview, breakdown, sources, release };

async function boot() {
  const screenEl = document.getElementById('screen');
  const segmentsEl = document.getElementById('segments');
  const headerDateEl = document.getElementById('headerDate');
  const offlineBanner = document.getElementById('offlineBanner');

  const [series, sourcesMeta, industries, segments, lastRun, releases] = await Promise.all([
    loadJson('./data/series.json'),
    loadJson('./data/sources.json'),
    loadJson('./data/industries.json'),
    loadJson('./data/segments.json'),
    loadJson('./data/last_run.json'),
    loadJson('./data/releases.json'),
  ]);

  if (!navigator.onLine) offlineBanner.hidden = false;
  window.addEventListener('offline', () => { offlineBanner.hidden = false; });
  window.addEventListener('online', () => { offlineBanner.hidden = true; });

  if (series === null) {
    screenEl.textContent = '데이터를 불러올 수 없습니다. 네트워크 연결을 확인한 뒤 다시 시도해 주세요.';
    return;
  }

  if (lastRun && lastRun.run_at) {
    headerDateEl.textContent = `${lastRun.run_at.slice(5, 7)}.${lastRun.run_at.slice(8, 10)} 갱신`;
  }

  const months = monthOptions(series);
  const ctx = {
    series,
    sources: sourcesMeta || [],
    industries: industries || [],
    segments: segments || [],
    // 월별 보도자료 색인. 없으면(수집 전이거나 게시판이 죽었으면) 빈 객체로
    // 두고 카드가 게시판 목록으로 떨어진다.
    releases: releases || {},
    months,
    state: { period: months.latest, breakdown: null, category: null, releaseCode: null },
    rerender: () => route(),
  };

  const sheet = mountSheet(document.getElementById('sheet'),
    document.getElementById('sheetHandle'),
    document.getElementById('sheetHandleLabel'),
    document.getElementById('sheetScrim'), ctx);

  function route() {
    const parsed = parseRoute(location.hash);
    ctx.state.breakdown = parsed.name === 'breakdown' ? parsed.params.breakdown : null;
    ctx.state.category = parsed.name === 'breakdown' ? parsed.params.category : null;
    ctx.state.releaseCode = parsed.name === 'release' ? parsed.params.code : null;
    // 활성 탭은 화면 이름이 아니라 parsed.segment 로 고른다 — 보도자료 화면은
    // 총괄의 아래층이라 거기 있는 동안 총괄 탭이 켜져 있어야 한다.
    segmentsEl.querySelectorAll('.segment').forEach(el => {
      el.classList.toggle('segment--active', el.dataset.route === parsed.segment);
    });
    screenEl.innerHTML = '';
    (screens[parsed.name] || overview)(screenEl, ctx);
    sheet.refresh();
  }

  window.addEventListener('hashchange', route);
  route();
}

if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('./sw.js').catch(() => {});
}

boot();

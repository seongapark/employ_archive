// 앱 셸. 해시 라우팅과 데이터 로드만 한다 — 무엇을 그리는지는 screens/ 가 안다.
import { loadJson } from '../core/shell.js';
import { parseRoute } from './route.js';
import * as home from './screens/home.js';
import * as picks from './screens/picks.js';
import * as topics from './screens/topics.js';
import * as orgs from './screens/orgs.js';
import * as report from './screens/report.js';

const screens = { home, picks, topics, orgs, report };

function setActiveTab(tabbarEl, tab) {
  tabbarEl.querySelectorAll('.tab').forEach((el) => {
    el.classList.toggle('tab--active', el.dataset.route === tab);
  });
}

async function start() {
  const screenEl = document.getElementById('screen');
  const tabbarEl = document.getElementById('tabbar');
  const countEl = document.getElementById('headerCount');
  const offlineEl = document.getElementById('offlineBanner');

  const [reports, boards, orgList, lastRun, picksData] = await Promise.all([
    loadJson('./data/reports.json'),
    loadJson('./data/boards.json'),
    loadJson('./data/orgs.json'),
    loadJson('./data/last_run.json'),
    // 추천 판정은 실제로 돌려야 생긴다. 판정 전에는 파일이 없어 404 이고,
    // loadJson 이 그때 null 을 돌려주므로 아래에서 {} 로 받는다.
    loadJson('./data/recommendations.json'),
  ]);

  if (!reports) {
    screenEl.innerHTML = '<div class="empty">데이터를 불러올 수 없습니다.<br>네트워크 연결을 확인한 뒤 다시 시도해 주세요.</div>';
    return;
  }
  if (!navigator.onLine) offlineEl.hidden = false;
  countEl.textContent = `${reports.length}건`;

  const ctx = {
    reports,
    boards: boards || [],
    orgs: orgList || [],
    lastRun: lastRun || {},
    picks: picksData || {},
    abstracts: null,
    state: { q: '', orgs: [], years: [], sort: 'score', expanded: new Set() },
    route: parseRoute(location.hash),
    refreshBody: null,
    prefetchAbstracts,
  };

  let abstractsPromise = null;
  function prefetchAbstracts() {
    // 초록은 첫 화면에 필요 없다. 검색창에 포커스가 가는 순간 받기 시작하면
    // 타이핑을 시작할 때는 이미 와 있다.
    if (abstractsPromise) return abstractsPromise;
    abstractsPromise = loadJson('./data/abstracts.json').then((data) => {
      ctx.abstracts = data || {};
      // 검색 중이었다면 본문만 다시 그린다. 화면을 갈면 조합이 끊긴다.
      if (ctx.refreshBody) ctx.refreshBody();
      return ctx.abstracts;
    });
    return abstractsPromise;
  }

  // route 는 **화면을 바꿀 때만** 부른다. 같은 화면 안의 갱신(타이핑·칩·접기)은
  // 각 화면이 자기 본문만 다시 그린다 — 여기서 통째로 갈면 입력창이 교체돼
  // 한글 조합이 끊긴다.
  function route() {
    ctx.route = parseRoute(location.hash);
    ctx.refreshBody = null;
    setActiveTab(tabbarEl, ctx.route.tab);
    const fn = (screens[ctx.route.name] || screens.home).render;
    screenEl.scrollTop = 0;
    screenEl.innerHTML = '';
    fn(screenEl, ctx);
    // 상세로 들어왔는데 초록이 아직 없으면 그때 받는다.
    if (ctx.route.name === 'report' && !ctx.abstracts) {
      prefetchAbstracts().then(() => route());
    }
  }

  window.addEventListener('hashchange', () => route());
  window.addEventListener('online', () => { offlineEl.hidden = true; });
  window.addEventListener('offline', () => { offlineEl.hidden = false; });
  route();

  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('./sw.js').catch(() => {});
  }
}

start();

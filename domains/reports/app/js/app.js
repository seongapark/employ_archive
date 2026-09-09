// 앱 셸. 해시 라우팅과 데이터 로드만 한다 — 무엇을 그리는지는 screens/ 가 안다.
import { loadJson } from '../core/shell.js';
import * as home from './screens/home.js';
import * as topics from './screens/topics.js';
import * as orgs from './screens/orgs.js';
import * as report from './screens/report.js';

const screens = { home, topics, orgs, report };

function parseRoute(hash) {
  const h = (hash || '').replace(/^#/, '') || '/';
  if (h === '/' || h === '') return { name: 'home', param: null, tab: 'home' };
  const [, head, ...rest] = h.split('/');
  const param = rest.length ? rest.join('/') : null;
  if (head === 'topics') return { name: 'topics', param, tab: 'topics' };
  if (head === 'orgs') return { name: 'orgs', param, tab: 'orgs' };
  if (head === 'r') return { name: 'report', param: param && decodeURIComponent(param), tab: null };
  return { name: 'home', param: null, tab: 'home' };
}

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

  const [reports, boards, orgList, lastRun] = await Promise.all([
    loadJson('./data/reports.json'),
    loadJson('./data/boards.json'),
    loadJson('./data/orgs.json'),
    loadJson('./data/last_run.json'),
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
    abstracts: null,
    state: { q: '', orgs: [], years: [], sort: 'score', expanded: new Set() },
    route: parseRoute(location.hash),
    rerender: () => route({ keepFocus: false }),
    prefetchAbstracts,
  };

  let abstractsPromise = null;
  function prefetchAbstracts() {
    // 초록은 첫 화면에 필요 없다. 검색창에 포커스가 가는 순간 받기 시작하면
    // 타이핑을 시작할 때는 이미 와 있다.
    if (abstractsPromise) return abstractsPromise;
    abstractsPromise = loadJson('./data/abstracts.json').then((data) => {
      ctx.abstracts = data || {};
      if (ctx.route.name === 'home' && ctx.state.q) route({ keepFocus: true });
      return ctx.abstracts;
    });
    return abstractsPromise;
  }

  function route(opts = {}) {
    ctx.route = parseRoute(location.hash);
    setActiveTab(tabbarEl, ctx.route.tab);
    const fn = (screens[ctx.route.name] || screens.home).render;
    const active = document.activeElement;
    const caret = active && active.id === 'q' ? active.selectionStart : null;
    // 접힌 묶음을 펼치는 것은 화면을 바꾸는 게 아니라 보고 있던 자리를 여는
    // 것이다. 맨 위로 튕기면 572줄 목록에서 접기가 쓸모없어진다.
    const keptScroll = screenEl.scrollTop;
    if (!opts.keepFocus && !opts.keepScroll) screenEl.scrollTop = 0;
    screenEl.innerHTML = '';
    fn(screenEl, ctx);
    if (opts.keepScroll) screenEl.scrollTop = keptScroll;
    if (opts.keepFocus) {
      const input = screenEl.querySelector('#q');
      if (input) {
        input.focus();
        if (caret != null) input.setSelectionRange(caret, caret);
      }
    }
    // 상세로 들어왔는데 초록이 아직 없으면 그때 받는다.
    if (ctx.route.name === 'report' && !ctx.abstracts) {
      prefetchAbstracts().then(() => route({ keepFocus: false }));
    }
  }

  ctx.rerender = route;
  window.addEventListener('hashchange', () => route());
  window.addEventListener('online', () => { offlineEl.hidden = true; });
  window.addEventListener('offline', () => { offlineEl.hidden = false; });
  route();

  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('./sw.js').catch(() => {});
  }
}

start();

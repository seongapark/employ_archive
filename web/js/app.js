import { render as home } from './screens/home.js';
import { render as org } from './screens/org.js';
import { render as compare } from './screens/compare.js';
import { render as timeline } from './screens/timeline.js';

const screens = { home, org, compare, timeline };

async function loadJson(path) {
  // 배포(사이트 루트에 data/ 복사)에선 ./data/…, 로컬(저장소 루트 서빙)에선 ../data/… 폴백
  for (const base of ['./', '../']) {
    try {
      const res = await fetch(base + path, { cache: 'no-cache' });
      if (res.ok) return await res.json();
    } catch { /* 다음 후보 */ }
  }
  return null;
}

function computeDefaultYear(records, today) {
  const todayYear = parseInt(today.slice(0, 4), 10);
  const nextYear = todayYear + 1;
  const years = records.map(r => r.target_year);
  if (years.includes(nextYear)) return nextYear;
  if (years.length) return Math.max(...years);
  return nextYear;
}

function computeHeaderDate(records) {
  const withDate = records.filter(r => r.collected_at);
  if (!withDate.length) return '';
  const max = withDate.reduce((a, b) => (b.collected_at > a.collected_at ? b : a));
  const month = max.collected_at.slice(5, 7);
  const day = max.collected_at.slice(8, 10);
  return `${month}.${day} 갱신`;
}

function parseRoute(hash) {
  const h = (hash || '').replace(/^#/, '') || '/';
  if (h === '/' || h === '') return { name: 'home', params: {} };
  const orgMatch = h.match(/^\/org\/(.+)$/);
  if (orgMatch) return { name: 'org', params: { org: decodeURIComponent(orgMatch[1]) } };
  if (h === '/org') return { name: 'org-redirect', params: {} };
  if (h === '/compare') return { name: 'compare', params: {} };
  if (h === '/timeline') return { name: 'timeline', params: {} };
  return { name: 'home', params: {} };
}

function setActiveTab(tabbarEl, routeName) {
  const tabName = routeName === 'org-redirect' ? 'org' : routeName;
  tabbarEl.querySelectorAll('.tab').forEach(tab => {
    tab.classList.toggle('tab--active', tab.dataset.route === tabName);
  });
}

// 타임라인 화면은 픽셀 스펙(Timeline.dc.html)에서 전역 헤더 타이틀을 '최근 발표'로
// 표시한다. org 화면은 자체 뒤로가기 헤더를 화면 안에서 그리므로(org.js) 전역
// 타이틀은 건드리지 않고 기본값 '고용전망'을 유지한다.
export function headerTitleFor(routeName) {
  return routeName === 'timeline' ? '최근 발표' : '고용전망';
}

async function boot() {
  const offlineBanner = document.getElementById('offlineBanner');
  const screenEl = document.getElementById('screen');
  const tabbarEl = document.getElementById('tabbar');
  const headerDateEl = document.getElementById('headerDate');
  const headerTitleEl = document.getElementById('headerTitle');

  const [records, orgs, indicators, schedule] = await Promise.all([
    loadJson('data/forecasts.json'),
    loadJson('data/orgs.json'),
    loadJson('data/indicators.json'),
    loadJson('data/schedule.json'),
  ]);

  const anyMissing = records === null || orgs === null || indicators === null || schedule === null;
  if (anyMissing) {
    offlineBanner.hidden = false;
  }

  if (records === null) {
    screenEl.textContent = '데이터를 불러올 수 없습니다. 네트워크 연결을 확인한 뒤 다시 시도해 주세요.';
    return;
  }

  const safeOrgs = orgs || [];
  const safeIndicators = indicators || [];
  const safeSchedule = schedule || [];

  const today = new Date(Date.now() + 9 * 3600 * 1000).toISOString().slice(0, 10);
  const defaultYear = computeDefaultYear(records, today);

  headerDateEl.textContent = computeHeaderDate(records);

  const state = {
    indicator: 'emp_change',
    year: defaultYear,
    compare: {
      indicator: 'gdp_growth',
      year: defaultYear,
      filter: 'all',
    },
  };

  const ctx = {
    records,
    orgs: safeOrgs,
    indicators: safeIndicators,
    indicatorMeta: Object.fromEntries(safeIndicators.map(i => [i.code, i])),
    schedule: safeSchedule,
    today,
    state,
    params: {},
    navigate,
    rerender,
  };

  function navigate(hash) {
    location.hash = hash;
  }

  function findFirstOrgWithData() {
    for (const o of ctx.orgs) {
      if (ctx.records.some(r => r.org === o.org)) return o.org;
    }
    if (ctx.records.length) return ctx.records[0].org;
    return null;
  }

  function route() {
    const parsed = parseRoute(location.hash);

    if (parsed.name === 'org-redirect') {
      const firstOrg = findFirstOrgWithData();
      if (firstOrg) {
        location.hash = `#/org/${encodeURIComponent(firstOrg)}`;
      } else {
        location.hash = '#/';
      }
      return; // hashchange가 다시 route()를 호출한다
    }

    ctx.params = parsed.params;
    setActiveTab(tabbarEl, parsed.name);
    headerTitleEl.textContent = headerTitleFor(parsed.name);

    const screenFn = screens[parsed.name] || home;
    screenEl.innerHTML = '';
    screenFn(screenEl, ctx);
  }

  function rerender() {
    route();
  }

  window.addEventListener('hashchange', route);
  route();
}

if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('./sw.js').catch(() => {});
}

boot();

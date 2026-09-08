import { render as home } from './screens/home.js';
import { render as articles } from './screens/articles.js';
import { render as follow } from './screens/follow.js';
import { render as rounds } from './screens/rounds.js';
import { roundSwitchHtml, bindRoundSwitch } from './ui.js';
import { loadJson } from '../core/shell.js';

const screens = { home, articles, follow, rounds };

// 헤더 날짜는 '수집기가 마지막으로 돈 날'(last_run.json 의 run_at)이다.
// 회차의 배포일이 아니다 — 배포일을 쓰면 수집기가 죽어도 날짜가 그대로라
// 고장이 가려진다. 허브와 다른 도메인 앱도 같은 근거를 쓴다.
function computeHeaderDate(lastRun) {
  const at = lastRun && lastRun.run_at;
  if (!at) return '';
  return `${at.slice(5, 7)}.${at.slice(8, 10)} 갱신`;
}

function parseRoute(hash) {
  const h = (hash || '').replace(/^#/, '') || '/';
  if (h === '/' || h === '') return { name: 'home', params: {} };
  const artMatch = h.match(/^\/articles(?:\/(.+))?$/);
  if (artMatch) {
    let kw = null;
    if (artMatch[1]) {
      try {
        kw = decodeURIComponent(artMatch[1]);
      } catch {
        kw = null;              // 깨진 해시로 화면이 죽지 않게 한다
      }
    }
    return { name: 'articles', params: { kw } };
  }
  if (h === '/follow') return { name: 'follow', params: {} };
  if (h === '/rounds') return { name: 'rounds', params: {} };
  return { name: 'home', params: {} };
}

function setActiveTab(tabbarEl, routeName) {
  tabbarEl.querySelectorAll('.tab').forEach((tab) => {
    tab.classList.toggle('tab--active', tab.dataset.route === routeName);
  });
}

// 헤더는 '지금 어느 앱에 있나'를 말한다. 탭 이름은 탭바가 이미 말하고 있으므로
// 헤더까지 따라 바뀌면 도메인 이름이 화면에서 사라진다 — 홈으로 나가는 길을
// 잃는다. 다른 도메인 앱도 이 규칙을 따른다.
export function headerTitleFor() {
  return '행통 모니터링';
}

async function boot() {
  const offlineBanner = document.getElementById('offlineBanner');
  const screenEl = document.getElementById('screen');
  const tabbarEl = document.getElementById('tabbar');
  const headerDateEl = document.getElementById('headerDate');
  const headerTitleEl = document.getElementById('headerTitle');
  const switchEl = document.getElementById('roundSwitch');

  const [rounds_, arts, lastRun] = await Promise.all([
    loadJson('./data/rounds.json'),
    loadJson('./data/articles.json'),
    loadJson('./data/last_run.json'),
  ]);

  if (rounds_ === null || !navigator.onLine) offlineBanner.hidden = false;

  // network-first SW 는 오프라인에서도 캐시된 200 을 돌려주므로 loadJson 이
  // null 이 아닐 수 있다 — 배너는 online/offline 이벤트로 직접 토글한다.
  window.addEventListener('offline', () => { offlineBanner.hidden = false; });
  window.addEventListener('online', () => { offlineBanner.hidden = true; });

  if (rounds_ === null || rounds_.length === 0) {
    screenEl.innerHTML = '<div class="empty">데이터를 불러올 수 없습니다.<br>네트워크 연결을 확인한 뒤 다시 시도해 주세요.</div>';
    return;
  }

  headerDateEl.textContent = computeHeaderDate(lastRun);

  const ctx = {
    rounds: rounds_,
    articles: arts || {},
    state: {
      release: rounds_[0].release,   // rounds.json 은 최신 회차가 먼저다
      onlyCited: true,
      mode: 'regular',               // 기사 화면: 정기 / 후속
    },
    params: {},
    navigate: (hash) => { location.hash = hash; },
    rerender: () => route(),
  };

  function route() {
    const parsed = parseRoute(location.hash);
    ctx.params = parsed.params;
    setActiveTab(tabbarEl, parsed.name);
    headerTitleEl.textContent = headerTitleFor();

    // 회차 스위치는 셸에 있어 화면이 바뀌어도 살아남는다. 다만 회차 화면에서
    // 카드를 눌러 회차를 바꾸는 길이 있으므로, 고른 값은 매번 다시 맞춰 준다.
    switchEl.innerHTML = roundSwitchHtml(ctx);
    bindRoundSwitch(switchEl, ctx);

    const fn = screens[parsed.name] || home;
    screenEl.innerHTML = '';
    screenEl.scrollTop = 0;
    fn(screenEl, ctx);
  }

  window.addEventListener('hashchange', route);
  route();
}

if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('./sw.js').catch(() => {});
}

boot();

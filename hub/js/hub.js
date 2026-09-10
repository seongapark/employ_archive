import { loadJson } from '../core/shell.js';
import { DOMAINS, domainState, updatedLabel, askHref } from './state.js';

function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
  ));
}

async function render() {
  const list = document.getElementById('domains');
  if (!list) return;

  for (const d of DOMAINS) {
    const lastRun = await loadJson(`./${d.slug}/data/last_run.json`);
    const ready = domainState(lastRun) === 'ready';

    const el = document.createElement(ready ? 'a' : 'div');
    el.className = ready ? 'domain' : 'domain domain--pending';
    if (ready) el.href = `./${d.slug}/`;
    el.innerHTML = `
      <div class="domain__name">${esc(d.name)}</div>
      <div class="domain__desc">${esc(d.desc)}</div>
      <div class="domain__meta num">${esc(updatedLabel(lastRun))}</div>`;
    list.appendChild(el);
  }
}

// ── 앱 설치 버튼 ──────────────────────────────────────────────────────────
// 크롬 메뉴(⋮ → 앱 설치)는 찾기 어렵고, 폰에서는 '바로가기 만들기' 와 헷갈린다.
// 설치할 수 있을 때만 버튼을 보인다 — 이미 설치했거나 조건이 안 되면 크롬이
// beforeinstallprompt 를 안 주므로 버튼도 안 뜬다. 없는 기능을 그리지 않는다.
//
// **이 리스너는 모듈 최상단에서 걸어야 한다.** 크롬은 이 이벤트를 페이지가 뜨자마자
// 한 번 주고 만다 — 나중에 걸면 이미 지나간 뒤라 영영 못 받는다.
let 설치이벤트 = null;
const 설치버튼 = () => document.getElementById('install');

window.addEventListener('beforeinstallprompt', (e) => {
  e.preventDefault();                 // 크롬 기본 배너 대신 우리 버튼으로 받는다
  설치이벤트 = e;
  const b = 설치버튼();
  if (b) b.hidden = false;
});

window.addEventListener('appinstalled', () => {
  설치이벤트 = null;
  const b = 설치버튼();
  if (b) b.hidden = true;
});

document.getElementById('install')?.addEventListener('click', async () => {
  if (!설치이벤트) return;
  설치이벤트.prompt();
  await 설치이벤트.userChoice;        // 수락이든 거절이든 이벤트는 한 번뿐이다
  설치이벤트 = null;
  const b = 설치버튼();
  if (b) b.hidden = true;
});

render();

document.getElementById('askform')?.addEventListener('submit', (e) => {
  e.preventDefault();
  const href = askHref(document.getElementById('askq').value);
  if (href) location.href = href;
});

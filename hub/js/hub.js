import { loadJson } from '../core/shell.js';
import { DOMAINS, cardModel, 갱신상태, askHref } from './state.js';

function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
  ));
}

// 카드를 **먼저 다 그리고**(이름·설명은 네트워크가 필요 없다) 갱신 날짜와 링크만
// 나중에 채운다. 요청 넷은 동시에 나간다 — 예전에는 하나씩 기다렸다 붙여서 카드가
// 뚝뚝 끊어지며 나타났다.
function 카드그리기(m) {
  const el = document.createElement('a');
  el.className = 'domain domain--pending';
  el.innerHTML = `
    <div class="domain__name">${esc(m.name)}</div>
    <div class="domain__desc">${esc(m.desc)}</div>
    <div class="domain__meta num">${esc(m.meta)}</div>`;
  return el;
}

function 카드채우기(el, m) {
  el.className = m.ready ? 'domain' : 'domain domain--pending';
  // 아직 안 받았거나 수집이 한 번도 안 돈 도메인은 링크를 걸지 않는다 —
  // 빈 화면으로 보내는 것보다 못 들어가는 편이 정직하다.
  if (m.href) el.href = m.href;
  else el.removeAttribute('href');
  el.querySelector('.domain__meta').textContent = m.meta;
}

async function render() {
  const list = document.getElementById('domains');
  if (!list) return;

  // 1) 뼈대를 한 번에 붙인다. 프래그먼트로 모아 붙여 리플로가 한 번만 일어난다.
  const frag = document.createDocumentFragment();
  const els = DOMAINS.map((d) => {
    const el = 카드그리기(cardModel(d, null));
    frag.appendChild(el);
    return el;
  });
  list.appendChild(frag);

  // 2) 넷을 동시에 받아 채운다.
  const 결과 = await 갱신상태(loadJson);
  결과.forEach((lastRun, i) => 카드채우기(els[i], cardModel(DOMAINS[i], lastRun)));
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

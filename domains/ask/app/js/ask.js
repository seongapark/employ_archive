import { badgeLabel, understandLine, evidenceColumns } from './badge.js';
import { renderAll } from './render.js';

// Worker 배포 주소. 배포되기 전에는 알 수 없다 — 실제 주소를 지어내지 않는다.
// TODO(배포 후): domains/ask/worker 를 `wrangler deploy` 한 뒤 나오는 실제
// *.workers.dev(또는 커스텀 도메인) 주소로 이 상수를 바꾼다.
const API = 'https://REPLACE-AFTER-DEPLOY.workers.dev/api/ask';

function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function setBusy(busy) {
  document.getElementById('qform').classList.toggle('qform--busy', busy);
  document.getElementById('q').disabled = busy || !navigator.onLine;
}

function renderError(message) {
  document.getElementById('understand').hidden = true;
  document.getElementById('badges').innerHTML = '';
  document.getElementById('answer').innerHTML = '';
  document.getElementById('evidence').innerHTML = `<p class="error">${esc(message)}</p>`;
  document.getElementById('limits').innerHTML = '';
  document.getElementById('sources').innerHTML = '';
  document.getElementById('followups').innerHTML = '';
}

async function 물어본다(payload) {
  const res = await fetch(API, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return res.json();
}

async function go(q, 유형 = null, 슬롯 = null) {
  setBusy(true);
  try {
    const 카드 = await 물어본다(슬롯 ? { 유형, 슬롯 } : { q });
    if (카드?.오류) {
      renderError('질의 처리 중 오류가 발생했다 — 잠시 후 다시 시도한다');
      return;
    }
    renderAll(카드, { esc, badgeLabel, understandLine, evidenceColumns, go });
  } catch {
    renderError('서버에 연결하지 못했다 — 네트워크 상태를 확인한다');
  } finally {
    setBusy(false);
  }
}

document.getElementById('qform').addEventListener('submit', (e) => {
  e.preventDefault();
  const q = document.getElementById('q').value.trim();
  if (q) { location.hash = `#/q=${encodeURIComponent(q)}`; go(q); }
});

function fromHash() {
  const m = location.hash.match(/^#\/?q=(.+)$/);
  if (!m) return;
  const q = decodeURIComponent(m[1]);
  document.getElementById('q').value = q;
  go(q);
}

function updateOnlineState() {
  const offline = !navigator.onLine;
  document.getElementById('offline').hidden = !offline;
  document.getElementById('q').disabled = offline;
}

window.addEventListener('online', updateOnlineState);
window.addEventListener('offline', updateOnlineState);
window.addEventListener('hashchange', fromHash);

updateOnlineState();
fromHash();

if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('./sw.js').catch(() => {});
}

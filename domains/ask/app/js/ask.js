import { badgeLabel, understandLine, evidenceColumns } from './badge.js';
import { renderAll } from './render.js';

// Worker 배포 주소. 워커를 다시 배포해 주소가 바뀌면 이 한 줄을 고친다.
// 워커 쪽 CORS 는 wrangler.jsonc 의 ASK_ALLOWED_ORIGIN 이 정한다 — 둘이 어긋나면
// 브라우저가 응답을 못 읽는다(서버는 200 을 내는데 화면만 빈다).
const API = 'https://employ-archive-ask.seongapark92.workers.dev/api/ask';

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
  // Minor(최종 리뷰): 여기서 #conflicts 를 안 지우면, 성공 → 오류 순으로 물었을 때
  // 이전 질문의 "출처 간 상충" 이 오류 화면에 그대로 남는다.
  document.getElementById('conflicts').innerHTML = '';
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

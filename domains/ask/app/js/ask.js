import { badgeLabel } from './badge.js';
import { 묶음HTML, 답변HTML, 질문해시 } from './lookup.js';

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

// 출처 탐색 + 요약. 유형·슬롯을 보내지 않는 이유는 워커가 질문 원문에서 코드로
// 슬롯을 뽑기 때문이다 — 분해에는 LLM 을 안 쓴다(요약에만 쓴다).
async function go(q) {
  setBusy(true);
  try {
    const r = await 물어본다({ q });
    if (r?.오류) {
      renderError('질의 처리 중 오류가 발생했다 — 잠시 후 다시 시도한다');
      return;
    }
    document.getElementById('understand').hidden = true;
    document.getElementById('answer').innerHTML = '';
    document.getElementById('limits').innerHTML = '';
    document.getElementById('sources').innerHTML = '';
    document.getElementById('conflicts').innerHTML = '';
    document.getElementById('followups').innerHTML = '';
    document.getElementById('badges').innerHTML = (r.배지 ?? [])
      .map((c) => { const b = badgeLabel(c); return `<span class="badge badge--${b.색}">${esc(b.라벨)}</span>`; })
      .join('');
    // 문장이 먼저, 출처가 아래다. 문장이 없으면(한도초과·요약실패·검증실패) 이
    // 자리는 비고 CSS 가 블록을 감춘다 — 출처는 그대로 남는다.
    document.getElementById('answer').innerHTML = 답변HTML(r, { esc });
    document.getElementById('evidence').innerHTML = 묶음HTML(r, { esc });
  } catch {
    renderError('서버에 연결하지 못했다 — 네트워크 상태를 확인한다');
  } finally {
    setBusy(false);
  }
}

document.getElementById('qform').addEventListener('submit', (e) => {
  e.preventDefault();
  const q = document.getElementById('q').value.trim();
  if (!q) return;
  // **한 번 누르면 한 번만 보낸다.** 해시를 바꾸면 `hashchange` 가 `fromHash` 를 통해
  // `go` 를 부른다 — 여기서 또 부르면 요청이 두 번 나간다. 워커 로그로 확인했다:
  // 한 번 눌렀는데 POST 가 2건이었다(2026-09-13). 문장을 두 번 만들어 **LLM 비용이
  // 두 배**였고, 화면은 늦게 온 응답으로 한 번 더 덮였다.
  // 같은 질문을 다시 누르면 해시가 안 바뀌어 `hashchange` 가 안 오므로 그때만 직접 부른다.
  const 해시 = 질문해시(q);
  if (location.hash === 해시) go(q);
  else location.hash = 해시;
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

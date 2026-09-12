import { 기간선택, 순서, 이름, 도메인현황 } from './model.js';
import { 요약HTML, 도메인HTML, 화면HTML, 유입HTML, 분포HTML, 잠금HTML, 도구HTML, 현황HTML }
  from './render.js';
import { 막대SVG } from './chart.js';
import { 불러오기, 토큰쓰기, 토큰지우기, 주인등록, 주인상태, 현황불러오기 } from './api.js';

const 화면 = () => document.getElementById('screen');
const 탭바 = () => document.getElementById('tabs');
let 현재일수 = 기간선택.find((x) => x.기본).days;
let 현재탭 = '현황';

// 마지막으로 받은 것을 들고 있는다. **탭을 옮길 때 다시 받지 않기 위해서다** —
// 두 화면은 서로 다른 곳(워커 / 정적 JSON)에서 오는데, 탭을 누를 때마다 둘 다
// 다시 부르면 누를 때마다 기다려야 하고 D1 조회도 두 배가 된다.
let 마지막 = { 통계: null, 현황: [], 오류: null };

const 안내 = {
  미배포: '워커가 아직 배포되지 않았다 — domains/admin/DEPLOY.md 의 절차를 끝내야 한다.',
  연결실패: '서버에 연결하지 못했다 — 네트워크 상태를 확인한다.',
};

// ── 탭별 내용 ────────────────────────────────────────────────────────────
// 두 함수 모두 끝에 도구(로그아웃·제외 상태)를 붙인다. 어느 탭에 있든 빠져나갈
// 길이 있어야 하고, 한쪽에만 두면 그 탭을 안 보는 동안 로그아웃할 방법이 없다.

function 현황화면() {
  return `${현황HTML(마지막.현황)}${도구HTML(주인상태(localStorage))}`;
}

function 방문화면() {
  // 워커가 죽었거나 아직 배포 전이면 숫자가 없다. 그 사실만 말하고 도구는 남긴다.
  if (마지막.오류) {
    return `<p class="empty">${안내[마지막.오류]}</p>${도구HTML(주인상태(localStorage))}`;
  }
  const s = 마지막.통계;
  return `
    <nav class="periods">${기간선택.map((p) => `
      <button class="period${p.days === 현재일수 ? ' period--on' : ''}"
        data-days="${p.days}" type="button">${p.label}</button>`).join('')}</nav>
    ${요약HTML(s)}
    <h2 class="sec">도메인별</h2>${도메인HTML(s)}
    <h2 class="sec">일별 추이</h2>
    <div class="trend">${막대SVG(s.일별, 순서, { width: 320, height: 120 })}</div>
    <div class="legend">${순서.map((k) => `
      <span class="legend__i"><i style="background:var(--dom-${k})"></i>${이름[k] ?? k}</span>`).join('')}</div>
    <h2 class="sec">화면</h2>${화면HTML(s)}
    <h2 class="sec">유입</h2>${유입HTML(s)}
    <h2 class="sec">방문자</h2>${분포HTML(s)}
    ${도구HTML(주인상태(localStorage))}`;
}

function 그리기() {
  const nav = 탭바();
  nav.hidden = false;
  for (const b of nav.querySelectorAll('.segment')) {
    b.classList.toggle('segment--active', b.dataset.tab === 현재탭);
    b.setAttribute('aria-selected', String(b.dataset.tab === 현재탭));
  }
  화면().scrollTop = 0;   // 탭을 옮기면 위에서부터 본다
  화면().innerHTML = 현재탭 === '현황' ? 현황화면() : 방문화면();
}

function 잠그기() {
  탭바().hidden = true;   // 비밀번호를 넣기 전에는 보여 줄 탭이 없다
  화면().innerHTML = 잠금HTML();
}

async function 새로고침() {
  const fetch1 = globalThis.fetch.bind(globalThis);
  const r = await 불러오기(현재일수, { fetch: fetch1, store: localStorage });
  if (r.상태 === '인증') { 잠그기(); return; }

  // 도메인 현황은 정적 JSON 만 읽으므로 워커가 죽어 있어도(미배포·연결실패)
  // 봐야 한다 — 그래서 r.상태 분기 밖에서, 잠금 화면이 아닌 한 항상 부른다.
  마지막.현황 = 도메인현황(await 현황불러오기({ fetch: fetch1 }));

  if (r.상태 === 'ok') {
    // 집계를 성공적으로 받은 뒤에만 등록을 시도한다 — 인증 실패·미배포·연결실패
    // 상태에서는 시도하지 않는다(토큰이 없거나 워커가 없다). 그리기() 전에
    // await 해 두면 도구HTML 이 방금 등록된 상태를 바로 보여준다.
    await 주인등록(localStorage, { fetch: fetch1 });
    마지막.통계 = r.통계;
    마지막.오류 = null;
  } else {
    마지막.통계 = null;
    마지막.오류 = r.상태;
  }
  그리기();
}

// ── 이벤트 ───────────────────────────────────────────────────────────────
// 화면을 다시 그릴 때마다 리스너를 새로 걸지 않는다 — 한 번만 위임한다.

// 탭바는 `.screen` 밖에 있으므로 리스너도 따로 건다. 탭만 바꾸는 것은 이미 받아
// 둔 것을 다시 그리는 일이라 네트워크를 타지 않는다 — 누르면 곧바로 바뀐다.
탭바().addEventListener('click', (e) => {
  const b = e.target.closest('.segment');
  if (!b || b.dataset.tab === 현재탭) return;
  현재탭 = b.dataset.tab;
  그리기();
});

화면().addEventListener('click', (e) => {
  const p = e.target.closest('.period');
  if (p) { 현재일수 = Number(p.dataset.days); 새로고침(); return; }
  if (e.target.id === 'logout') { 토큰지우기(localStorage); 잠그기(); }
});
화면().addEventListener('submit', (e) => {
  if (e.target.id !== 'unlock') return;
  e.preventDefault();
  const v = e.target.querySelector('#token').value.trim();
  if (v) { 토큰쓰기(localStorage, v); 새로고침(); }
});

새로고침();

import { 기간선택, 순서 } from './model.js';
import { 요약HTML, 도메인HTML, 화면HTML, 유입HTML, 분포HTML, 잠금HTML } from './render.js';
import { 막대SVG } from './chart.js';
import { 불러오기, 토큰쓰기, 토큰지우기, 제외상태, 제외설정 } from './api.js';

const 화면 = () => document.getElementById('screen');
let 현재일수 = 기간선택.find((x) => x.기본).days;

const 안내 = {
  미배포: '워커가 아직 배포되지 않았다 — domains/admin/DEPLOY.md 의 절차를 끝내야 한다.',
  연결실패: '서버에 연결하지 못했다 — 네트워크 상태를 확인한다.',
};

function 그리기(s) {
  화면().innerHTML = `
    <nav class="periods">${기간선택.map((p) => `
      <button class="period${p.days === 현재일수 ? ' period--on' : ''}"
        data-days="${p.days}" type="button">${p.label}</button>`).join('')}</nav>
    ${요약HTML(s)}
    <h2 class="sec">도메인별</h2>${도메인HTML(s)}
    <h2 class="sec">일별 추이</h2>
    <div class="trend">${막대SVG(s.일별, 순서, { width: 320, height: 120 })}</div>
    <div class="legend">${순서.map((k) => `
      <span class="legend__i"><i style="background:var(--dom-${k})"></i>${k}</span>`).join('')}</div>
    <h2 class="sec">화면</h2>${화면HTML(s)}
    <h2 class="sec">유입</h2>${유입HTML(s)}
    <h2 class="sec">방문자</h2>${분포HTML(s)}
    <div class="tools">
      <label class="toggle"><input id="off" type="checkbox"${제외상태(localStorage) ? ' checked' : ''}>
        내 방문을 통계에서 뺀다</label>
      <button id="logout" class="toggle__btn" type="button">토큰 지우기</button>
    </div>`;
}

async function 새로고침() {
  const r = await 불러오기(현재일수, { fetch: globalThis.fetch.bind(globalThis),
    store: localStorage });
  if (r.상태 === '인증') 화면().innerHTML = 잠금HTML();
  else if (r.상태 === 'ok') 그리기(r.통계);
  else 화면().innerHTML = `<p class="empty">${안내[r.상태]}</p>`;
}

// 화면을 다시 그릴 때마다 리스너를 새로 걸지 않는다 — 한 번만 위임한다.
화면().addEventListener('click', (e) => {
  const p = e.target.closest('.period');
  if (p) { 현재일수 = Number(p.dataset.days); 새로고침(); return; }
  if (e.target.id === 'logout') { 토큰지우기(localStorage); 새로고침(); }
});
화면().addEventListener('change', (e) => {
  if (e.target.id === 'off') 제외설정(localStorage, e.target.checked);
});
화면().addEventListener('submit', (e) => {
  if (e.target.id !== 'unlock') return;
  e.preventDefault();
  const v = e.target.querySelector('#token').value.trim();
  if (v) { 토큰쓰기(localStorage, v); 새로고침(); }
});

새로고침();

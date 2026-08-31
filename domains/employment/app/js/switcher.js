// 기준월 스위처. 총괄과 속성별이 같은 것을 쓴다.
//
// 화면마다 복사해 두면 한쪽만 고쳐지는 날이 온다 — 연도를 바꿀 때 그 해에 없는
// 달로 떨어지지 않게 맞춰주는 규칙이 여기 들어 있어서 특히 그렇다.
//
// 두 화면이 같은 ctx.state.period 를 본다. 속성별에서 달을 바꾸면 총괄도 그 달을
// 보게 되는데, 그게 맞다 — 화면이 다르다고 "지금 보고 있는 달" 이 둘일 이유가 없다.
// (시트의 점선만 따로 논다. 그건 시계열을 훑는 도구라 화면의 달과 분리했다.)

import { esc } from './data.js';

export function switcherHtml(ctx) {
  const { years, monthsByYear } = ctx.months;
  const year = Number(ctx.state.period.slice(0, 4));
  const month = Number(ctx.state.period.slice(5, 7));
  const yearOpts = years.map(y =>
    `<option value="${y}"${y === year ? ' selected' : ''}>${esc(String(y))}년</option>`).join('');
  const monthOpts = (monthsByYear[year] || []).map(m =>
    `<option value="${m}"${m === month ? ' selected' : ''}>${esc(String(m))}월</option>`).join('');
  return `<div class="switcher">
    <select class="switcher__year" aria-label="기준 연도">${yearOpts}</select>
    <select class="switcher__month" aria-label="기준 월">${monthOpts}</select>
  </div>`;
}

export function bindSwitcher(el, ctx) {
  const year = el.querySelector('.switcher__year');
  const month = el.querySelector('.switcher__month');
  if (!year || !month) return;

  year.addEventListener('change', e => {
    // 그 해에 없는 달로 떨어지지 않게 한다. 2024년은 7~12월뿐이고 2026년은
    // 1~7월뿐이라, 달을 그대로 들고 넘어가면 빈 화면이 된다.
    const y = Number(e.target.value);
    const months = ctx.months.monthsByYear[y] || [];
    const m = months[months.length - 1];
    ctx.state.period = `${y}-${String(m).padStart(2, '0')}`;
    ctx.rerender();
  });
  month.addEventListener('change', e => {
    ctx.state.period = `${ctx.state.period.slice(0, 4)}-${String(e.target.value).padStart(2, '0')}`;
    ctx.rerender();
  });
}

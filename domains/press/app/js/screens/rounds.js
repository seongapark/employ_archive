import { esc, dayLabel, youthShare, citeRate } from '../data.js';
import { card, section } from '../ui.js';

// 회차 화면은 '이 달이 지난 달과 어떻게 다른가'만 본다.
// 회차가 하나뿐이면 비교가 아니라 그 사실을 말한다.

function compareBars(rounds, pick, label, unit) {
  const vals = rounds.map((r) => ({ label: r.label, n: pick(r) }));
  const max = vals.reduce((m, v) => Math.max(m, v.n), 0);
  const rows = vals.map((v) => `
    <div class="bar-row" style="grid-template-columns:62px 1fr 40px;">
      <div class="bar-row__name">${esc(v.label)}</div>
      <div class="bar-row__track${v.n === 0 ? ' bar-row__track--zero' : ''}">
        ${v.n > 0 ? `<div class="bar-row__fill" style="width:${max ? Math.round((v.n / max) * 100) : 0}%;"></div>` : ''}
      </div>
      <div class="bar-row__n num">${v.n}${esc(unit)}</div>
    </div>`).join('');
  return `<div style="margin-bottom:10px;">
    <div class="sec-title">${esc(label)}</div><div class="bars">${rows}</div></div>`;
}

function roundRow(r, ctx) {
  const f = r.follow;
  const top = r.outside.slice(0, 3).map((x) => `${x.w} ${x.n}`).join(' · ');
  return `<button type="button" class="card" data-release="${esc(r.release)}"
      style="display:flex;flex-direction:column;gap:3px;text-align:left;width:100%;cursor:pointer;">
    <div style="display:flex;align-items:baseline;justify-content:space-between;">
      <div style="font-size:13px;font-weight:700;">${esc(r.label)}</div>
      <div class="num" style="font-size:11px;color:var(--text-muted);">${esc(dayLabel(r.release))} 배포</div>
    </div>
    <div style="display:flex;align-items:baseline;gap:8px;">
      <div class="num" style="font-size:22px;font-weight:700;">${r.regular.cited}</div>
      <div style="font-size:11px;color:var(--text-secondary);">인용 기사 · 언론사 ${r.regular.press}곳 · 인용률 ${citeRate(r)}%</div>
    </div>
    <div style="font-size:11px;color:var(--frame-fg);">${esc(top || '밖 표현 없음')}</div>
    <div style="font-size:11px;color:var(--text-muted);">
      청년 비중 ${youthShare(r)}% · 후속 ${f ? `${f.cited}건` : '미수집'}</div>
  </button>`;
}

export function render(root, ctx) {
  const rounds = ctx.rounds.slice().sort((a, b) => (a.release < b.release ? -1 : 1));
  const list = ctx.rounds.map((r) => roundRow(r, ctx)).join('');

  const compare = rounds.length > 1 ? card(`
    <div style="font-size:13px;font-weight:700;margin-bottom:8px;">회차 비교</div>
    ${compareBars(rounds, (r) => r.regular.cited, '인용 기사 수', '건')}
    ${compareBars(rounds, (r) => r.regular.press, '보도 언론사', '곳')}
    ${compareBars(rounds, youthShare, '청년 보도 비중', '%')}
    ${compareBars(rounds, citeRate, '인용률 — 수집한 것 중 실제 인용', '%')}
    <div style="font-size:10px;color:var(--text-muted);">
      인용률이 낮은 회차는 그날 고용보험 관련 다른 기사가 많았다는 뜻입니다.</div>`) : '';

  root.innerHTML = section(`${compare}${list}`);

  root.querySelectorAll('[data-release]').forEach((el) => {
    el.addEventListener('click', () => {
      ctx.state.release = el.dataset.release;
      ctx.navigate('#/');
    });
  });
}

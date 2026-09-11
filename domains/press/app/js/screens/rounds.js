import { esc, dayLabel, youthShare, citeRate } from '../data.js';
import { card, columnChart, section } from '../ui.js';

// 회차 화면은 '이 달이 지난 달과 어떻게 다른가'만 본다.
// 회차가 하나뿐이면 비교가 아니라 그 사실을 말한다.

// 화면에 세울 회차 수. 회차는 매달 하나씩 늘기만 하므로 상한이 필요하다 —
// 2년이면 24개가 되고, 휴대폰에서 기둥 하나가 12px 이 되어 라벨이 안 들어간다.
// 가로 막대로 두면 24줄이 되어 같은 문제가 세로로 생긴다.
export const MAX_COLS = 12;

/** '26.8월분 → 8월. 기둥 폭이 좁아 연도까지는 못 싣는다(정렬이 곧 연도다). */
function shortLabel(label) {
  const m = String(label).match(/([0-9]+)월/);
  return m ? `${m[1]}월` : String(label);
}

/** 최근 MAX_COLS 회차만. 잘라낸 사실은 화면이 말한다. */
export function recent(rounds, max = MAX_COLS) {
  return rounds.slice(Math.max(0, rounds.length - max));
}

function compareChart(rounds, pick, label, unit) {
  return columnChart(label,
    rounds.map((r) => ({ name: shortLabel(r.label), n: pick(r) })), { unit });
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

  const shown = recent(rounds);
  const cut = rounds.length - shown.length;
  const cutLine = cut
    ? `<div style="font-size:10px;color:var(--text-muted);">
         회차 ${rounds.length}개 중 최근 ${shown.length}개만 그렸습니다 · 아래 목록에는 전부 있습니다</div>` : '';

  const compare = rounds.length > 1 ? card(`
    <div style="font-size:13px;font-weight:700;margin-bottom:8px;">회차 비교</div>
    ${compareChart(shown, (r) => r.regular.cited, '인용 기사 수', '건')}
    ${compareChart(shown, (r) => r.regular.press, '보도 언론사', '곳')}
    ${compareChart(shown, youthShare, '청년 보도 비중', '%')}
    ${compareChart(shown, citeRate, '인용률 — 수집한 것 중 실제 인용', '%')}
    <div style="font-size:10px;color:var(--text-muted);">
      인용률이 낮은 회차는 그날 고용보험 관련 다른 기사가 많았다는 뜻입니다.</div>
    ${cutLine}`) : '';

  root.innerHTML = section(`${compare}${list}`);

  root.querySelectorAll('[data-release]').forEach((el) => {
    el.addEventListener('click', () => {
      ctx.state.release = el.dataset.release;
      ctx.navigate('#/');
    });
  });
}

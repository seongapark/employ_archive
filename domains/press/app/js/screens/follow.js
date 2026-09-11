import { esc, roundOf, dayLabel, daysSince, isCited } from '../data.js';
import { articleRow, card, section, trendChart } from '../ui.js';

// 이 화면은 '배포하고 나서 3주 동안 무슨 일이 있었나'만 본다.
// 배포 당일(정기)은 기사 화면이 맡는다 — 두 화면이 같은 것을 보면
// 어느 쪽을 봐야 하는지 알 수 없다.

// 그래프에 세울 표현 수. 검증을 통과한 색이 여섯이고, 선이 그보다 많아지면
// 어느 선이 어느 말인지 못 가른다.
const MAX_LINES = 6;

function trendCard(round, ctx) {
  // 소멸한 표현은 싣지 않는다. 하루 쓰이고 만 말은 볼 일이 아니고,
  // 목록이 길어지면 살아남은 것이 묻힌다. 다만 몇 개를 뺐는지는 말한다 —
  // 빈 표와 '소멸만 있었다'는 다른 사실이다.
  // **소멸한 표현도 그린다.** 표에서는 뺐었다 — 행이 늘면 살아남은 것이 묻혔다.
  // 선에서는 반대다: 0 으로 가라앉는 선이 있어야 살아남은 선이 도드라진다.
  // 배포 당일에 많이 쓰인 순으로 여섯까지.
  const top = (round.frames || []).slice(0, MAX_LINES);
  if (!top.length) {
    return card(`
      <div style="font-size:13px;font-weight:700;">후속 보도 추세</div>
      <div style="font-size:12px;color:var(--text-secondary);margin-top:6px;">
        배포 당일에 두 곳 이상이 함께 쓴 표현이 없습니다.</div>`);
  }

  return card(`
    <div style="font-size:13px;font-weight:700;margin-bottom:6px;">후속 보도 추세</div>
    ${trendChart(top, { picked: ctx.state.trendKw || null })}`);
}

// **인용한 기사만 싣는다.** 배포 당일(기사 화면)은 그날 같이 돈 것을 맥락으로
// 남기지만, 후속 구간은 3주라 인용 아닌 기사가 그냥 그 기간의 고용 기사
// 전부가 된다 — 맥락이 아니라 잡음이고, 이 회차가 어디까지 번졌나를 덮는다.
function timeline(round, ctx) {
  const bundle = ctx.articles[round.release] || { follow: [] };
  const cited = (bundle.follow || []).filter(isCited);
  if (!cited.length) return '';

  const byDay = new Map();
  cited.slice().sort((a, b) => (a.pub < b.pub ? 1 : -1)).forEach((a) => {
    const d = a.pub.slice(0, 10);
    if (!byDay.has(d)) byDay.set(d, []);
    byDay.get(d).push(a);
  });

  const blocks = [...byDay.entries()].map(([d, arts]) => {
    const n = daysSince(round.release, d);
    return `<div class="tl__day">
      <div class="tl__mark">
        <span class="tl__date num">${esc(dayLabel(d))}</span>
        ${n === null ? '' : `<span class="tl__dplus num">D+${n}</span>`}
        <span class="tl__count num">${arts.length}건</span>
      </div>
      <div class="tl__arts">${arts.map(articleRow).join('')}</div>
    </div>`;
  }).join('');

  return card(`
    <div style="font-size:13px;font-weight:700;margin-bottom:2px;">후속 기사</div>
    <div class="artmeta" style="margin:0 0 8px 0;">
      인용 ${cited.length}건 · 보도자료 배포일부터 3주간 매일 수집합니다</div>
    <div class="tl">${blocks}</div>`);
}

export function render(root, ctx) {
  const round = roundOf(ctx.rounds, ctx.state.release);
  if (!round) {
    root.innerHTML = '<div class="empty">회차가 없습니다.</div>';
    return;
  }

  if (!round.follow) {
    root.innerHTML = section(`<div class="empty">
      후속 수집은 배포 이튿날부터 매일 돕니다.<br>
      ${esc(round.label)} 회차는 아직 첫 수집 전입니다.</div>`);
    return;
  }

  root.innerHTML = section(`${trendCard(round, ctx)}${timeline(round, ctx)}`);

  // 범례를 누르면 그 선만 남는다. 선이 여섯이면 겹치는 구간에서 어느 것이
  // 어느 것인지 눈으로 못 따라간다 — 하나씩 떼어 볼 길이 있어야 한다.
  root.querySelectorAll('.tr__key').forEach((el) => {
    el.addEventListener('click', () => {
      const kw = el.dataset.kw;
      ctx.state.trendKw = ctx.state.trendKw === kw ? null : kw;
      ctx.rerender();
    });
  });
}

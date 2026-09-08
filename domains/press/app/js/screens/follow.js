import { esc, roundOf, dayLabel, daysSince } from '../data.js';
import { articleRow, card, section } from '../ui.js';

// 이 화면은 '배포하고 나서 보름 동안 무슨 일이 있었나'만 본다.
// 배포 당일(정기)은 기사 화면이 맡는다 — 두 화면이 같은 것을 보면
// 어느 쪽을 봐야 하는지 알 수 없다.

const STATE_CLS = { 확산: 'state--spread', 유지: 'state--hold' };

function aliveTable(round) {
  // 소멸한 표현은 싣지 않는다. 하루 쓰이고 만 말은 볼 일이 아니고,
  // 목록이 길어지면 살아남은 것이 묻힌다. 다만 몇 개를 뺐는지는 말한다 —
  // 빈 표와 '소멸만 있었다'는 다른 사실이다.
  const alive = round.frames.filter((f) => f.state !== '소멸');
  const gone = round.frames.length - alive.length;
  const goneLine = gone
    ? `<div style="font-size:10px;color:var(--text-muted);margin-top:6px;">
         배포 당일에만 쓰이고 사라진 표현 ${gone}개는 뺐습니다</div>` : '';

  if (!alive.length) {
    return card(`
      <div style="font-size:13px;font-weight:700;">살아남은 표현</div>
      <div style="font-size:12px;color:var(--text-secondary);margin-top:6px;">
        배포 당일에 쓰인 표현이 후속 구간까지 이어진 것은 없습니다.</div>
      ${goneLine}`);
  }

  const rows = alive.map((f) => `
    <tr>
      <td><span class="art__tag">${esc(f.kw)}</span></td>
      <td class="num">${f.d0}</td>
      <td class="num" style="font-weight:700;">${f.later}</td>
      <td class="num" style="color:var(--text-secondary);">${esc(dayLabel(f.last))}</td>
      <td><span class="state ${STATE_CLS[f.state] || 'state--hold'}">${esc(f.state)}</span></td>
    </tr>`).join('');

  return card(`
    <div style="font-size:13px;font-weight:700;">살아남은 표현</div>
    <div style="font-size:11px;color:var(--text-secondary);margin:2px 0 6px;">
      배포 당일 보도자료 밖에서 나온 말이 그 뒤에도 쓰였나</div>
    <table class="tbl">
      <tr><th>표현</th><th>당일</th><th>이후</th><th>최근</th><th></th></tr>
      ${rows}
    </table>
    <div style="font-size:10px;color:var(--text-muted);margin-top:6px;">
      「이후」가 「당일」 이상이면 확산 · 후속 구간 ${esc(round.follow.window.join(' ~ '))}</div>
    ${goneLine}`);
}

function timeline(round, ctx) {
  const bundle = ctx.articles[round.release] || { follow: [] };
  const cited = (bundle.follow || []).filter((a) => a.cites);
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
    <div style="font-size:11px;color:var(--text-secondary);margin-bottom:8px;">
      인용 ${cited.length}건 · 최근 날짜부터</div>
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
      후속 수집을 아직 안 돌렸습니다.<br>
      후속 구간은 배포 다음날부터 15일까지라, ${esc(round.label)} 회차는
      그 구간이 끝난 뒤에 채워집니다.</div>`);
    return;
  }

  root.innerHTML = section(`${aliveTable(round)}${timeline(round, ctx)}`);
}

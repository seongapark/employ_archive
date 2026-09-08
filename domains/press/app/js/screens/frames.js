import { esc, roundOf, dayLabel, daysSince } from '../data.js';
import { articleRow, card, section } from '../ui.js';

// 프레임 화면은 '배포 당일에 생긴 말이 며칠째 살아있나'만 본다.
// 후속 수집이 없는 회차는 표가 아니라 '아직 못 잰다'고 말한다 — 빈 표는
// '프레임이 없다'로 읽히는데 그건 사실이 아니다.

const STATE_CLS = { 확산: 'state--spread', 유지: 'state--hold', 소멸: 'state--gone' };

function frameTable(round) {
  const rows = round.frames.map((f) => `
    <tr>
      <td><span class="art__tag">${esc(f.kw)}</span></td>
      <td class="num">${f.d0}</td>
      <td class="num">${f.later}</td>
      <td class="num" style="color:var(--text-secondary);">${esc(f.first ? dayLabel(f.first) : '—')}</td>
      <td class="num" style="color:var(--text-secondary);">${esc(f.last ? dayLabel(f.last) : '—')}</td>
      <td><span class="state ${STATE_CLS[f.state] || 'state--gone'}">${esc(f.state)}</span></td>
    </tr>`).join('');
  return card(`
    <div style="font-size:13px;font-weight:700;margin-bottom:6px;">배포 당일 밖 표현이 며칠째 살아있나</div>
    <table class="tbl">
      <tr><th>표현</th><th>당일</th><th>이후</th><th>첫 등장</th><th>최근</th><th>상태</th></tr>
      ${rows}
    </table>
    <div style="font-size:10px;color:var(--text-muted);margin-top:6px;">
      「이후」가 「당일」 이상이면 확산, 0이면 소멸 · 후속 구간 ${esc(round.follow.window.join(' ~ '))}</div>`);
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
    return `<div style="padding:8px 0;border-top:1px solid var(--border);">
      <div style="font-size:11px;font-weight:600;color:var(--text-secondary);">
        <span class="num">${esc(dayLabel(d))}</span>${n === null ? '' : ` · D+${n}`} · ${arts.length}건</div>
      ${arts.slice(0, 3).map(articleRow).join('')}</div>`;
  }).join('');
  return card(`<div style="font-size:13px;font-weight:700;">후속 기사 타임라인</div>${blocks}
    <div style="font-size:10px;color:var(--text-muted);margin-top:6px;">날짜별 3건까지</div>`);
}

export function render(root, ctx) {
  const round = roundOf(ctx.rounds, ctx.state.release);
  if (!round) {
    root.innerHTML = '<div class="empty">회차가 없습니다.</div>';
    return;
  }

  const body = round.follow && round.frames.length
    ? `${frameTable(round)}${timeline(round, ctx)}`
    : `<div class="empty">
        ${round.follow ? '이 회차는 배포 당일에 반복된 밖 표현이 없었습니다.'
                       : `후속 수집을 아직 안 돌렸습니다.<br>후속 구간은 배포 다음날부터 15일까지라, ${esc(round.label)} 회차는 그 구간이 끝난 뒤에 채워집니다.`}
      </div>`;

  root.innerHTML = `${section(body)}`;
}

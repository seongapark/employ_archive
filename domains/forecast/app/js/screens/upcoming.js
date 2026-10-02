// 발표 예정 일정표. 타임라인의 '다음 발표 예정' 띠를 누르면 온다.
//
// 데이터는 data/upcoming.json(pipeline/calendar.write_upcoming, 매일 수집이 다시 쓴다).
// 기관이 미리 알린 날은 그 날짜를(공지), 나머지는 최근 2년 같은 달 발표일에
// 앞뒤 사흘을 붙인 구간을(예상) 보인다. 예상을 하루로 찍지 않는다 — 찍으면
// 그날 안 나왔을 때 화면이 틀린 말을 한 셈이 된다.
import { esc } from '../data.js';

function mmdd(day) {
  return `${day.slice(5, 7)}.${day.slice(8, 10)}`;
}

export function whenText(entry) {
  return entry.date ? mmdd(entry.date) : `${mmdd(entry.start)}~${mmdd(entry.end)}`;
}

const keyOf = entry => entry.date || entry.start;
const sorted = entries => [...entries].sort((a, b) => keyOf(a).localeCompare(keyOf(b)));

export function upcomingGroups(entries) {
  const groups = [];
  for (const entry of sorted(entries || [])) {
    const key = keyOf(entry);
    const month = `${key.slice(0, 4)}년 ${Number(key.slice(5, 7))}월`;
    if (!groups.length || groups[groups.length - 1].month !== month) groups.push({ month, entries: [] });
    groups[groups.length - 1].entries.push(entry);
  }
  return groups;
}

// 아직 지나지 않은 가장 가까운 회차. 예상 구간은 끝나기 전까지 '다음' 이다.
export function nextEntry(entries, today) {
  return sorted(entries || []).find(e => (e.date || e.end) >= today) || null;
}

function badge(entry) {
  const announced = entry.basis === '공지';
  const style = announced
    ? 'color:#ffffff;background:var(--accent);'
    : 'color:var(--text-secondary);background:#eef0f3;';
  return `<span style="font-size:11px;font-weight:700;padding:1px 7px;border-radius:999px;${style}">${esc(entry.basis)}</span>`;
}

function row(entry) {
  return `
    <button type="button" class="card" data-org="${esc(entry.org)}" style="display:flex;align-items:center;gap:10px;text-align:left;width:100%;cursor:pointer;min-height:44px;">
      <div style="flex:1;min-width:0;">
        <div style="font-size:14px;font-weight:700;">${esc(entry.org_name_ko)} <span style="font-weight:600;">${esc(entry.report)}</span></div>
      </div>
      <div class="num" style="font-size:13px;font-weight:600;color:#344054;white-space:nowrap;">${esc(whenText(entry))}</div>
      ${badge(entry)}
    </button>`;
}

export function renderList(entries) {
  return upcomingGroups(entries).map((group, i) => `
    <div class="num" style="font-size:12px;font-weight:700;color:var(--text-secondary);${i ? 'margin-top:4px;' : ''}">${esc(group.month)}</div>
    ${group.entries.map(row).join('')}`).join('');
}

export function render(el, ctx) {
  const entries = (ctx.upcoming && ctx.upcoming.entries) || [];
  const months = (ctx.upcoming && ctx.upcoming.months) || 6;
  const list = entries.length
    ? renderList(entries)
    : '<div style="padding:32px 0;text-align:center;font-size:14px;color:var(--text-secondary);">예정된 발표가 없습니다</div>';
  el.innerHTML = `
    <div style="display:flex;flex-direction:column;gap:8px;padding:12px 16px;">
      <a href="#/timeline" style="font-size:13px;font-weight:600;color:var(--accent);text-decoration:none;">← 최근 발표</a>
      <div style="font-size:13px;color:var(--text-secondary);">앞으로 ${esc(String(months))}개월 동안 나올 전망 보고서입니다.</div>
      ${list}
      <p style="margin:8px 0 0;font-size:12px;line-height:1.6;color:var(--text-secondary);">
        <b>공지</b>는 기관이 미리 알린 발표일입니다. <b>예상</b>은 최근 2년 같은 달 발표일에
        앞뒤 사흘을 더한 구간으로, 실제 날짜는 달라질 수 있습니다.</p>
    </div>`;
  el.querySelectorAll('[data-org]').forEach(card => {
    card.addEventListener('click', () => ctx.navigate('#/org/' + encodeURIComponent(card.dataset.org)));
  });
}

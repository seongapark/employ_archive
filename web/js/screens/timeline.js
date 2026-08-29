import { timelineGroups, fmtValue, fmtDelta, isNew, esc } from '../data.js';

const CONF_LABEL = {
  verified: 'API 검증',
  extracted: '자동추출',
  reviewed: '확인완료',
};

const ABBR = {
  emp_change: '취업자',
  unemp_rate: '실업률',
  gdp_growth: '성장률',
  cpi: '물가',
  emp_rate: '고용률',
  emp_rate_youth: '청년고용률',
  labor_force: '경활참가율',
};

// 요약 줄 전용 소형 삼각형 (org.js/home.js의 10x9 배지형보다 작은 8x7 인라인 아이콘)
const DELTA_SVG_SMALL = {
  up: '<svg width="8" height="7" viewBox="0 0 10 9"><polygon points="5,0 10,9 0,9" fill="#c73e3a"></polygon></svg>',
  down: '<svg width="8" height="7" viewBox="0 0 10 9"><polygon points="0,0 10,0 5,9" fill="#2f6bd0"></polygon></svg>',
};

function mmdd(dateStr) {
  const [, m, d] = dateStr.split('-');
  return `${m}.${d}`;
}

function findNextSchedule(schedule, today) {
  const upcoming = (schedule || [])
    .filter(s => s.date >= today)
    .sort((a, b) => a.date.localeCompare(b.date));
  return upcoming[0] || null;
}

function renderBanner(entry) {
  if (!entry) return '';
  const text = `다음 발표 예정 — ${entry.org_name_ko} ${entry.report} ${mmdd(entry.date)}`;
  return `
    <div style="margin:12px 16px 0 16px;padding:10px 14px;background:var(--accent-light);border-radius:10px;display:flex;align-items:center;gap:8px;">
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#23508f" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="5" width="18" height="16" rx="1"></rect><line x1="3" y1="10" x2="21" y2="10"></line><line x1="8" y1="3" x2="8" y2="7"></line><line x1="16" y1="3" x2="16" y2="7"></line></svg>
      <div class="num" style="font-size:13px;font-weight:600;color:var(--accent);">${esc(text)}</div>
    </div>`;
}

function renderSummaryLine(items) {
  const parts = items.slice(0, 4).map(rec => {
    const abbr = ABBR[rec.indicator] || rec.indicator;
    const delta = fmtDelta(rec);
    const svg = (delta.dir === 'up' || delta.dir === 'down') ? ` ${DELTA_SVG_SMALL[delta.dir]}` : '';
    return `${esc(abbr)} ${esc(fmtValue(rec))}${svg}`;
  });
  return parts.join(' · ');
}

function renderEventCard(event, today) {
  const firstRec = event.items[0];
  const newBadge = isNew(firstRec, today);
  const title = event.report_title.startsWith(event.org_name_ko)
    ? event.report_title
    : `${event.org_name_ko} ${event.report_title}`;
  const confLabel = CONF_LABEL[firstRec.confidence] || firstRec.confidence || '';
  const subLine = `${mmdd(event.published_at)} · ${event.items.length}개 지표 갱신 · ${confLabel}`;
  const summaryHtml = renderSummaryLine(event.items);

  return `
    <button type="button" class="card" data-org="${esc(event.org)}" style="display:flex;flex-direction:column;gap:5px;text-align:left;width:100%;cursor:pointer;min-height:44px;">
      <div style="display:flex;align-items:center;gap:8px;">
        <div style="font-size:14px;font-weight:700;">${esc(title)}</div>
        ${newBadge ? '<div style="font-size:10px;font-weight:700;color:#ffffff;background:#c73e3a;padding:1px 7px;border-radius:999px;">NEW</div>' : ''}
      </div>
      <div class="num" style="font-size:12px;color:var(--text-secondary);">${esc(subLine)}</div>
      <div class="num" style="display:flex;align-items:center;flex-wrap:wrap;gap:4px;font-size:13px;color:#344054;">${summaryHtml}</div>
    </button>`;
}

function renderMonthGroup(group, today, isFirst) {
  const label = `<div class="num" style="font-size:12px;font-weight:700;color:var(--text-secondary);${isFirst ? '' : 'margin-top:4px;'}">${esc(group.month)}</div>`;
  const cards = group.events.map(event => renderEventCard(event, today)).join('');
  return label + cards;
}

export function render(el, ctx) {
  const { records, schedule, today } = ctx;
  const groups = timelineGroups(records);
  const nextEntry = findNextSchedule(schedule, today);

  let body;
  if (groups.length === 0) {
    body = `
      <div style="flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:6px;padding:32px 16px;text-align:center;">
        <div style="font-size:14px;font-weight:600;color:var(--text-secondary);">아직 수집된 전망이 없습니다</div>
      </div>`;
  } else {
    const rows = groups.map((g, i) => renderMonthGroup(g, today, i === 0)).join('');
    body = `<div style="flex:1;display:flex;flex-direction:column;gap:8px;padding:12px 16px;">${rows}</div>`;
  }

  el.innerHTML = `
    ${renderBanner(nextEntry)}
    ${body}
  `;

  el.querySelectorAll('[data-org]').forEach(card => {
    card.addEventListener('click', () => {
      ctx.navigate('#/org/' + card.dataset.org);
    });
  });
}

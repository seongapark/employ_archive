import { latestRecords, summarize, fmtValue, fmtNumber, fmtDelta, dateLabel, halfYearLabel, esc, SHORT_LABELS, isOcrSourced, OCR_WARNING_TITLE } from '../data.js';

// 홈의 첫 필만 목업대로 '취업자 증감'을 온전히 유지하고, 나머지는 공유 축약 라벨을 쓴다.
const PILLS = [
  { code: 'emp_change', label: '취업자 증감' },
  { code: 'unemp_rate', label: SHORT_LABELS.unemp_rate },
  { code: 'gdp_growth', label: SHORT_LABELS.gdp_growth },
  { code: 'cpi', label: SHORT_LABELS.cpi },
];

const BADGE = {
  verified: { cls: 'badge--verified', label: '검증' },
  extracted: { cls: 'badge--extracted', label: '자동' },
  reviewed: { cls: 'badge--reviewed', label: '확인' },
};

const DELTA_SVG = {
  up: '<svg width="10" height="9" viewBox="0 0 10 9"><polygon points="5,0 10,9 0,9" fill="#c73e3a"></polygon></svg>',
  down: '<svg width="10" height="9" viewBox="0 0 10 9"><polygon points="0,0 10,0 5,9" fill="#2f6bd0"></polygon></svg>',
  flat: '',
};

function yearsForIndicator(records, indicator) {
  const years = new Set(records.filter(r => r.indicator === indicator).map(r => r.target_year));
  return Array.from(years).sort((a, b) => a - b);
}

function renderPills(ctx) {
  const pills = PILLS.map(p => {
    const active = p.code === ctx.state.indicator;
    return `<button type="button" class="pill${active ? ' pill--active' : ''}" data-indicator="${esc(p.code)}" style="min-height:44px;">${esc(p.label)}</button>`;
  }).join('');
  return `<div style="display:flex;gap:8px;padding:10px 16px 4px 16px;overflow-x:auto;">${pills}</div>`;
}

function renderYearSwitch(year) {
  return `
    <div style="display:flex;align-items:center;justify-content:center;gap:18px;padding:8px 16px 4px 16px;">
      <button type="button" id="yearPrev" aria-label="이전 연도" style="display:flex;align-items:center;justify-content:center;width:44px;height:44px;background:none;border:none;color:#98a2b3;cursor:pointer;">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#98a2b3" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 18 9 12 15 6"></polyline></svg>
      </button>
      <div class="num" style="font-size:15px;font-weight:700;">${esc(String(year))}년 전망</div>
      <button type="button" id="yearNext" aria-label="다음 연도" style="display:flex;align-items:center;justify-content:center;width:44px;height:44px;background:none;border:none;color:#98a2b3;cursor:pointer;">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#98a2b3" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"></polyline></svg>
      </button>
    </div>`;
}

function renderBand(latest, indicatorMeta) {
  const summary = summarize(latest);
  if (!summary) return '';
  const unit = indicatorMeta ? indicatorMeta.unit : '';

  const titleText = summary.count === 1
    ? '1개 기관 수집'
    : `${summary.count}개 기관 평균 ${fmtNumber(summary.avg, unit)}${esc(unit)} <span style="font-weight:400;color:#667085;">· 발표시점 상이</span>`;

  const metaText = summary.count === 1
    ? ''
    : `<div class="band__meta num">최고 ${fmtNumber(summary.max.value, unit)} (${esc(summary.max.org_name_ko)}) · 최저 ${fmtNumber(summary.min.value, unit)} (${esc(summary.min.org_name_ko)})</div>`;

  return `
    <div class="band">
      <div class="band__title num">${titleText}</div>
      ${metaText}
    </div>`;
}

function renderCard(rec, ctx) {
  const badgeInfo = BADGE[rec.confidence] || { cls: 'badge--extracted', label: rec.confidence || '' };
  const delta = fmtDelta(rec);
  const deltaCls = delta.dir === 'up' ? 'delta-up' : delta.dir === 'down' ? 'delta-down' : 'delta-flat';
  const deltaSvg = DELTA_SVG[delta.dir] || '';
  const date = dateLabel(rec, ctx.orgs);
  const orgMeta = ctx.orgs.find(o => o.org === rec.org);
  const isApi = orgMeta && orgMeta.method === 'api';
  const rationale = rec.rationale && rec.rationale.trim()
    ? rec.rationale
    : (isApi ? `${rec.report_title} · API 수집` : rec.report_title);

  const [value, unitSuffix] = splitValueUnit(fmtValue(rec));
  const halves = halfYearLabel(ctx.records, rec);
  const ocrBadge = isOcrSourced(rec, ctx.orgs)
    ? `<div class="badge badge--ocr" title="${esc(OCR_WARNING_TITLE)}">확인필요</div>`
    : '';

  return `
    <button type="button" class="card" data-org="${esc(rec.org)}" style="display:flex;flex-direction:column;gap:4px;text-align:left;width:100%;cursor:pointer;">
      <div style="display:flex;align-items:center;justify-content:space-between;">
        <div style="font-size:13px;font-weight:600;">${esc(rec.org_name_ko)}</div>
        <div style="display:flex;align-items:center;gap:6px;">
          <div class="badge ${badgeInfo.cls}">${esc(badgeInfo.label)}</div>
          ${ocrBadge}
        </div>
      </div>
      <div style="display:flex;align-items:baseline;gap:10px;">
        <div class="num" style="font-size:28px;font-weight:700;">${esc(value)}<span style="font-size:15px;font-weight:600;">${esc(unitSuffix)}</span></div>
        <div class="delta ${deltaCls}">${deltaSvg}<span class="num">${esc(delta.text)}</span></div>
      </div>
      <div class="num" style="font-size:12px;color:#667085;">${esc(halves)}</div>
      <div style="display:flex;gap:8px;font-size:12px;color:#667085;">
        <span class="num">${esc(date)}</span><span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${esc(rationale)}</span>
      </div>
    </button>`;
}

function splitValueUnit(formatted) {
  const match = formatted.match(/^(-?[\d.]+)(.*)$/);
  if (!match) return [formatted, ''];
  return [match[1], match[2]];
}

function renderMissingRow(missingOrgs) {
  if (!missingOrgs.length) return '';
  const names = missingOrgs.map(o => o.name_ko).join(' · ');
  return `
    <div class="missing-row">
      <div class="missing-row__names">${esc(names)}</div>
      <div class="missing-row__label">이 지표 미제공</div>
    </div>`;
}

function lastCollectedLabel(records) {
  const withDate = records.filter(r => r.collected_at);
  if (!withDate.length) return '';
  const max = withDate.reduce((a, b) => (b.collected_at > a.collected_at ? b : a));
  return max.collected_at.slice(0, 16).replace('T', ' ');
}

export function render(el, ctx) {
  const { records, orgs, state } = ctx;

  if (!PILLS.some(p => p.code === state.indicator)) {
    state.indicator = 'emp_change';
  }

  const availableYears = yearsForIndicator(records, state.indicator);
  if (availableYears.length && !availableYears.includes(state.year)) {
    state.year = availableYears[availableYears.length - 1];
  }

  const latest = latestRecords(records, { indicator: state.indicator, targetYear: state.year });
  const indicatorMeta = ctx.indicatorMeta ? ctx.indicatorMeta[state.indicator] : null;

  const presentOrgs = new Set(latest.map(r => r.org));
  const missingOrgs = orgs.filter(o => !presentOrgs.has(o.org));

  let body;
  if (latest.length === 0) {
    const lastCollected = lastCollectedLabel(records);
    body = `
      <div style="flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:6px;padding:32px 16px;text-align:center;">
        <div style="font-size:14px;font-weight:600;color:#667085;">아직 수집된 전망이 없습니다</div>
        ${lastCollected ? `<div class="num" style="font-size:12px;color:#98a2b3;">마지막 수집 ${esc(lastCollected)}</div>` : ''}
      </div>`;
  } else {
    body = `
      <div style="flex:1;display:flex;flex-direction:column;gap:8px;padding:10px 16px 8px 16px;">
        ${latest.map(rec => renderCard(rec, ctx)).join('')}
        ${renderMissingRow(missingOrgs)}
      </div>`;
  }

  el.innerHTML = `
    ${renderPills(ctx)}
    ${renderYearSwitch(state.year)}
    ${renderBand(latest, indicatorMeta)}
    ${body}
  `;

  el.querySelectorAll('[data-indicator]').forEach(btn => {
    btn.addEventListener('click', () => {
      state.indicator = btn.dataset.indicator;
      ctx.rerender();
    });
  });

  const prevBtn = el.querySelector('#yearPrev');
  const nextBtn = el.querySelector('#yearNext');
  if (prevBtn) {
    prevBtn.addEventListener('click', () => {
      const years = yearsForIndicator(records, state.indicator);
      if (!years.length) return;
      const idx = years.indexOf(state.year);
      const nextIdx = idx <= 0 ? years.length - 1 : idx - 1;
      state.year = years[nextIdx];
      ctx.rerender();
    });
  }
  if (nextBtn) {
    nextBtn.addEventListener('click', () => {
      const years = yearsForIndicator(records, state.indicator);
      if (!years.length) return;
      const idx = years.indexOf(state.year);
      const nextIdx = idx === -1 || idx === years.length - 1 ? 0 : idx + 1;
      state.year = years[nextIdx];
      ctx.rerender();
    });
  }

  el.querySelectorAll('[data-org]').forEach(card => {
    card.addEventListener('click', () => {
      ctx.navigate('#/org/' + encodeURIComponent(card.dataset.org));
    });
  });
}

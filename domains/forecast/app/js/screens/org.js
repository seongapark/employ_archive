import { seriesFor, orgIndicators, fmtValue, fmtDelta, dateLabel, halfYearLabel, esc, SHORT_LABELS, rationaleFor } from '../data.js';

// 펼침 상태는 화면 방문 동안 유지 (모듈 스코프 — 여러 회차 행이 동시에 펼쳐질 수 있음)
const expandedIds = new Set();

const DELTA_SVG = {
  up: '<svg width="10" height="9" viewBox="0 0 10 9"><polygon points="5,0 10,9 0,9" fill="#c73e3a"></polygon></svg>',
  down: '<svg width="10" height="9" viewBox="0 0 10 9"><polygon points="0,0 10,0 5,9" fill="#2f6bd0"></polygon></svg>',
  flat: '<span style="color:#98a2b3;font-weight:700;">—</span>',
};

function mmdd(dateStr) {
  const [, m, d] = dateStr.split('-');
  return `${m}.${d}`;
}

function yymm(dateStr) {
  const [y, m] = dateStr.split('-');
  return `${y.slice(2)}.${m}`;
}

function yearsForOrg(records, org) {
  const years = new Set(records.filter(r => r.org === org).map(r => r.target_year));
  return Array.from(years).sort((a, b) => a - b);
}

function yearsForOrgIndicator(records, org, indicator) {
  const years = new Set(
    records.filter(r => r.org === org && r.indicator === indicator).map(r => r.target_year)
  );
  return Array.from(years).sort((a, b) => a - b);
}

function sparkline(values) {
  const w = 40, h = 14, pad = 1;
  let points;
  if (values.length < 2) {
    const y = h / 2;
    points = `${pad},${y} ${w - pad},${y}`;
  } else {
    const min = Math.min(...values);
    const max = Math.max(...values);
    const range = max - min || 1;
    const innerW = w - pad * 2;
    const innerH = h - pad * 2;
    points = values
      .map((v, i) => {
        const x = pad + (i / (values.length - 1)) * innerW;
        const y = max === min ? h / 2 : pad + (1 - (v - min) / range) * innerH;
        return `${x.toFixed(1)},${y.toFixed(1)}`;
      })
      .join(' ');
  }
  return `<svg width="40" height="14" viewBox="0 0 40 14" fill="none"><polyline points="${points}" stroke="#98a2b3" stroke-width="1.5"></polyline></svg>`;
}

function renderHeader(ctx, orgMeta, orgCode, latestRec, scheduleEntry) {
  const title = orgMeta ? orgMeta.name_ko : orgCode;
  const subParts = [];
  if (latestRec) subParts.push(`최근 ${dateLabel(latestRec, ctx.orgs)}`);
  if (scheduleEntry) subParts.push(`다음 ${mmdd(scheduleEntry.date)} 예정`);
  const sub = subParts.join(' · ');

  return `
    <div class="header" style="justify-content:flex-start;gap:10px;">
      <button type="button" id="backBtn" aria-label="뒤로가기" style="display:flex;align-items:center;justify-content:center;width:44px;height:44px;margin:-4px 0 -4px -10px;background:none;border:none;cursor:pointer;color:var(--text);">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 18 9 12 15 6"></polyline></svg>
      </button>
      <div style="display:flex;flex-direction:column;">
        <div class="header__title">${esc(title)}</div>
        ${sub ? `<div class="header__meta num">${esc(sub)}</div>` : ''}
      </div>
    </div>`;
}

export function renderSummaryCard(ctx, orgCode, indicators, currentYear, records) {
  const items = [];
  for (const code of indicators) {
    const series = seriesFor(records, { org: orgCode, indicator: code, targetYear: currentYear });
    if (!series.length) continue;
    const latest = series[series.length - 1];
    const delta = fmtDelta(latest);
    const deltaSvg = DELTA_SVG[delta.dir] || '';
    // 지표명·수치는 절대 줄바꿈하지 않는다 — 좁은 폭에서 '취업 / 자',
    // '20만 / 명' 으로 쪼개지면 숫자가 세 줄이 되어 카드가 무너진다.
    // 대신 칸이 모자라면 아래 그리드가 2열에서 1열로 떨어진다.
    items.push(`
      <button type="button" class="num" data-indicator="${esc(code)}" style="display:flex;align-items:center;gap:6px;font-size:13px;background:none;border:none;padding:2px 0;text-align:left;cursor:pointer;min-height:44px;white-space:nowrap;">
        <span style="color:#667085;">${esc(SHORT_LABELS[code] || code)}</span>
        <span style="font-weight:700;">${esc(fmtValue(latest))}</span>
        ${deltaSvg}
        ${sparkline(series.map(r => r.value))}
      </button>`);
  }
  if (!items.length) return '';

  let basisDate = '';
  const orgYearRecs = records.filter(r => r.org === orgCode && r.target_year === currentYear);
  if (orgYearRecs.length) {
    const max = orgYearRecs.reduce((a, b) => (b.published_at > a.published_at ? b : a));
    basisDate = yymm(max.published_at);
  }

  // auto-fit — 한 칸에 160px 을 못 주면 2열이 1열로 떨어진다. 고정 2열이면
  // 좁은 폰에서 칸이 145px 까지 줄어 지표명과 수치가 각각 줄바꿈된다.
  return `
    <div class="card" style="margin:10px 16px 0 16px;padding:10px 14px;display:flex;flex-direction:column;gap:6px;">
      <div class="num" style="font-size:11px;font-weight:600;color:#667085;">${esc(String(currentYear))}년 전망${basisDate ? ` (${esc(basisDate)} 기준)` : ''}</div>
      <div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(160px, 1fr));gap:6px;">
        ${items.join('')}
      </div>
    </div>`;
}

// 지표는 필 나열이 아니라 드롭다운이다. 기관에 따라 지표가 다섯까지 가는데
// 필을 한 줄에 늘어놓으면 좁은 폰에서 가로 스크롤이 생기고 마지막 지표가
// 잘린다(실측: 360px 에서 '물가'가 잘렸다).
//
// 연도 묶음에는 flex:none 과 nowrap 을 함께 준다. flex 기본값(shrink 1)이면
// 옆 칸에 밀려 '2027' 과 '년' 이 두 줄로 쪼개진다 — 실제로 그랬다.
// 둘 중 하나만 걸면 안 된다: nowrap 만 주면 글자가 칸 밖으로 넘치고,
// flex:none 만 주면 폭이 더 좁아질 때 다시 깨진다.
function renderYearAndIndicator(currentYear, years, indicators, currentIndicator, ctx) {
  const hasYears = years.length > 0;
  const meta = ctx.indicatorMeta || {};
  const options = indicators.map(code => {
    const label = (meta[code] && meta[code].name_ko) || SHORT_LABELS[code] || code;
    return `<option value="${esc(code)}"${code === currentIndicator ? ' selected' : ''}>${esc(label)}</option>`;
  }).join('');

  const yearSwitch = hasYears
    ? `
      <div style="display:flex;align-items:center;gap:6px;flex:none;">
        <button type="button" id="yearPrev" aria-label="이전 연도" style="display:flex;align-items:center;justify-content:center;width:32px;height:44px;background:none;border:none;color:#98a2b3;cursor:pointer;flex:none;">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#98a2b3" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 18 9 12 15 6"></polyline></svg>
        </button>
        <div class="num" style="font-size:14px;font-weight:700;white-space:nowrap;">${esc(String(currentYear))}년</div>
        <button type="button" id="yearNext" aria-label="다음 연도" style="display:flex;align-items:center;justify-content:center;width:32px;height:44px;background:none;border:none;color:#98a2b3;cursor:pointer;flex:none;">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#98a2b3" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"></polyline></svg>
        </button>
      </div>`
    : '<div></div>';

  return `
    <div style="display:flex;align-items:center;justify-content:space-between;padding:10px 16px 2px 16px;gap:8px;">
      ${yearSwitch}
      <select id="indicatorSelect" class="num" aria-label="지표 선택" style="font-family:inherit;font-size:13px;font-weight:600;color:var(--text);background:var(--card);border:1px solid var(--border);padding:6px 10px;border-radius:8px;min-height:44px;min-width:0;flex:0 1 auto;">${options}</select>
    </div>`;
}

function renderChart(series) {
  if (series.length < 2) return '';

  const values = series.map(r => r.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const x0 = 30, x1 = 314;
  const yTop = 16, yBottom = 88;

  const pts = series.map((r, i) => {
    const x = x0 + (i / (series.length - 1)) * (x1 - x0);
    const y = max === min ? (yTop + yBottom) / 2 : yBottom - ((r.value - min) / range) * (yBottom - yTop);
    return { x, y, rec: r };
  });

  const lastIdx = pts.length - 1;
  const polyline = pts.map(p => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ');
  const circles = pts.map((p, i) => {
    if (i === lastIdx) {
      return `<circle cx="${p.x.toFixed(1)}" cy="${p.y.toFixed(1)}" r="5" fill="#23508f" stroke="#23508f" stroke-width="2"></circle>`;
    }
    return `<circle cx="${p.x.toFixed(1)}" cy="${p.y.toFixed(1)}" r="4" fill="#ffffff" stroke="#23508f" stroke-width="2"></circle>`;
  }).join('');
  const xLabels = pts.map(p => `<text x="${p.x.toFixed(1)}" y="103" font-size="10" fill="#98a2b3" text-anchor="middle">${esc(yymm(p.rec.published_at))}</text>`).join('');
  const lastPoint = pts[lastIdx];
  const labelY = Math.max(14, lastPoint.y - 10);
  const valueLabel = `<text x="${lastPoint.x.toFixed(1)}" y="${labelY.toFixed(1)}" font-size="11" font-weight="700" fill="#23508f" text-anchor="middle">${esc(fmtValue(lastPoint.rec))}</text>`;

  return `
    <div class="card" style="margin:8px 16px 0 16px;padding:12px 14px 6px 14px;">
      <svg width="100%" height="110" viewBox="0 0 330 110" fill="none">
        <line x1="8" y1="88" x2="322" y2="88" stroke="#e2e5ea" stroke-width="1"></line>
        <line x1="8" y1="52" x2="322" y2="52" stroke="#eef0f3" stroke-width="1"></line>
        <line x1="8" y1="16" x2="322" y2="16" stroke="#eef0f3" stroke-width="1"></line>
        <polyline points="${polyline}" stroke="#23508f" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round"></polyline>
        ${circles}
        ${xLabels}
        ${valueLabel}
      </svg>
    </div>`;
}

// B트랙(KEIS 등, method: "llm")은 스크래핑 문서에 대한 LLM 추출을 거치므로
// source_url/landing_url이 신뢰할 수 없는 채널에서 올 수 있다. javascript: 등
// 위험한 스킴이 href에 들어가지 않도록 http(s)만 허용한다.
function safeUrl(u) {
  return typeof u === 'string' && /^https?:\/\//i.test(u) ? u : null;
}

function renderSourceLine(rec) {
  const url = safeUrl(rec.source_url);
  if (url) {
    const pageSuffix = rec.source_page ? ` (p.${esc(String(rec.source_page))})` : '';
    return `
      <a href="${esc(url)}" target="_blank" rel="noopener" style="display:flex;align-items:center;gap:5px;font-size:12px;font-weight:600;color:var(--link);">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 3h7v7"></path><path d="M21 3 11 13"></path><path d="M19 14v6H4V5h6"></path></svg>
        원문 보기${pageSuffix} · ${esc(rec.report_title)}
      </a>`;
  }
  return `<div style="font-size:12px;color:#98a2b3;">원문 링크 확인 필요</div>`;
}

const CHEVRON = {
  down: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#98a2b3" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"></polyline></svg>',
  up: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#98a2b3" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="18 15 12 9 6 15"></polyline></svg>',
};

// 접힌 행에는 발표일·전망치·증감만 둔다. 근거 문장은 펼쳐야 나온다.
// 예전엔 근거를 접힌 행에 말줄임으로 밀어 넣었는데, 그 글자가 자리를 뺏어
// 수치가 '20 / 만 / 명' 세 줄로 쪼개졌다(360px 실측). 수치는 flex:none 이다.
//
// 수집 상태(자동/검증/확인, OCR 확인필요)는 어느 쪽에도 싣지 않는다 — 사용자 결정이다.
export function renderRow(rec, isExpanded, records, rationaleItems = []) {
  const delta = fmtDelta(rec);
  // DELTA_SVG.flat already renders its own "—", so don't also append delta.text
  // (which is also "—") — that would print it twice.
  const deltaMarkup = delta.dir === 'flat'
    ? DELTA_SVG.flat
    : `${DELTA_SVG[delta.dir] || ''}<span class="num">${esc(delta.text)}</span>`;
  const deltaColor = delta.dir === 'up' ? 'color:#c73e3a;' : delta.dir === 'down' ? 'color:#2f6bd0;' : '';
  const monthLabel = mmdd(rec.published_at);

  const summaryRow = (chevron, extra) => `
        <div class="num" style="font-size:13px;font-weight:600;color:#667085;width:42px;flex:none;">${esc(monthLabel)}</div>
        <div class="num" style="font-size:${extra};font-weight:700;flex:none;white-space:nowrap;">${esc(fmtValue(rec))}</div>
        <div class="delta" style="${deltaColor}flex:none;white-space:nowrap;">${deltaMarkup}</div>
        <div style="margin-left:auto;color:#98a2b3;flex:none;">${chevron}</div>`;

  if (isExpanded) {
    // 근거가 없는 회차는 근거 문단을 아예 그리지 않는다. 예전엔 보고서 제목으로
    // 떨어졌는데, 바로 아래 '원문 보기' 줄이 그 제목을 이미 말하고 있어서
    // 펼친 칸의 절반이 같은 문장 두 번이 됐다.
    const foundRationale = rationaleFor(rec, rationaleItems);
    const rationale = foundRationale && foundRationale.text
      ? `<div style="font-size:13px;line-height:1.5;color:#344054;">${esc(foundRationale.text)}</div>`
      : '';
    const tags = (foundRationale?.tags || []).map(t => `<div style="font-size:11px;color:#23508f;background:#e7edf6;padding:2px 8px;border-radius:999px;">${esc(t)}</div>`).join('');
    const landingUrl = safeUrl(rec.landing_url);
    const landing = landingUrl
      ? `<a href="${esc(landingUrl)}" target="_blank" rel="noopener" style="font-size:11px;color:#667085;">기관 자료실</a>`
      : '';
    return `
      <div class="card" style="border-color:#b9c9e2;display:flex;flex-direction:column;padding:0;">
        <button type="button" data-toggle="${esc(rec.id)}" style="display:flex;align-items:center;gap:10px;padding:10px 14px;background:none;border:none;width:100%;text-align:left;cursor:pointer;min-height:44px;">${summaryRow(CHEVRON.up, '17px')}
        </button>
        <div style="border-top:1px solid #eef0f3;padding:10px 14px;display:flex;flex-direction:column;gap:8px;">
          ${rationale}
          <div class="num" style="font-size:12px;color:#667085;">${esc(halfYearLabel(records, rec, { unit: true }))}</div>
          ${tags ? `<div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap;">${tags}</div>` : ''}
          ${renderSourceLine(rec)}
          ${landing}
        </div>
      </div>`;
  }

  return `
    <button type="button" class="card" data-toggle="${esc(rec.id)}" style="display:flex;align-items:center;gap:10px;padding:10px 14px;width:100%;text-align:left;cursor:pointer;">${summaryRow(CHEVRON.down, '15px')}
    </button>`;
}

function renderHistory(series, records, rationaleItems) {
  if (!series.length) {
    return `<div style="padding:16px;text-align:center;font-size:13px;color:#98a2b3;">이 연도에는 데이터가 없습니다</div>`;
  }
  const singleEdition = series.length === 1;
  const rows = series
    .slice()
    .reverse() // 최신 위
    .map(rec => renderRow(rec, singleEdition || expandedIds.has(rec.id), records, rationaleItems))
    .join('');
  return `<div style="display:flex;flex-direction:column;gap:6px;padding:8px 16px;">${rows}</div>`;
}

export function render(el, ctx) {
  const { records, state } = ctx;
  const orgCode = ctx.params.org;
  const orgMeta = ctx.orgs.find(o => o.org === orgCode);
  const orgRecords = records.filter(r => r.org === orgCode);

  if (orgRecords.length === 0) {
    el.innerHTML = `
      ${renderHeader(ctx, orgMeta, orgCode, null, null)}
      <div style="flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:6px;padding:32px 16px;text-align:center;">
        <div style="font-size:14px;font-weight:600;color:#667085;">수집된 데이터가 없습니다</div>
      </div>`;
    wireBack(el, ctx);
    return;
  }

  const indicators = orgIndicators(records, orgCode);
  if (indicators.length && !indicators.includes(state.indicator)) {
    state.indicator = indicators[0];
  }
  const currentIndicator = indicators.length ? state.indicator : null;

  const orgYears = yearsForOrg(records, orgCode);
  const indicatorYears = currentIndicator ? yearsForOrgIndicator(records, orgCode, currentIndicator) : orgYears;
  if (indicatorYears.length && !indicatorYears.includes(state.year)) {
    state.year = indicatorYears[indicatorYears.length - 1];
  }
  const currentYear = state.year;

  const latestRec = orgRecords.reduce((a, b) => (b.published_at > a.published_at ? b : a));
  const scheduleEntry = ctx.schedule.find(s => s.org === orgCode) || null;

  const seriesCurrent = currentIndicator
    ? seriesFor(records, { org: orgCode, indicator: currentIndicator, targetYear: currentYear })
    : [];

  el.innerHTML = `
    ${renderHeader(ctx, orgMeta, orgCode, latestRec, scheduleEntry)}
    ${renderSummaryCard(ctx, orgCode, indicators, currentYear, records)}
    ${indicators.length ? renderYearAndIndicator(currentYear, indicatorYears, indicators, currentIndicator, ctx) : ''}
    ${renderChart(seriesCurrent)}
    ${indicators.length ? renderHistory(seriesCurrent, ctx.records, ctx.rationales) : ''}
  `;

  wireBack(el, ctx);

  // 요약카드의 지표 항목은 여전히 눌러서 지표를 바꾸는 버튼이다.
  el.querySelectorAll('[data-indicator]').forEach(btn => {
    btn.addEventListener('click', () => {
      state.indicator = btn.dataset.indicator;
      ctx.rerender();
    });
  });

  const indicatorSelect = el.querySelector('#indicatorSelect');
  if (indicatorSelect) {
    indicatorSelect.addEventListener('change', () => {
      state.indicator = indicatorSelect.value;
      ctx.rerender();
    });
  }

  const prevBtn = el.querySelector('#yearPrev');
  const nextBtn = el.querySelector('#yearNext');
  if (prevBtn) {
    prevBtn.addEventListener('click', () => {
      const years = yearsForOrgIndicator(records, orgCode, currentIndicator);
      if (!years.length) return;
      const idx = years.indexOf(state.year);
      const nextIdx = idx <= 0 ? years.length - 1 : idx - 1;
      state.year = years[nextIdx];
      ctx.rerender();
    });
  }
  if (nextBtn) {
    nextBtn.addEventListener('click', () => {
      const years = yearsForOrgIndicator(records, orgCode, currentIndicator);
      if (!years.length) return;
      const idx = years.indexOf(state.year);
      const nextIdx = idx === -1 || idx === years.length - 1 ? 0 : idx + 1;
      state.year = years[nextIdx];
      ctx.rerender();
    });
  }

  el.querySelectorAll('[data-toggle]').forEach(row => {
    row.addEventListener('click', () => {
      const id = row.dataset.toggle;
      if (expandedIds.has(id)) {
        expandedIds.delete(id);
      } else {
        expandedIds.add(id);
      }
      ctx.rerender();
    });
  });
}

function wireBack(el, ctx) {
  const backBtn = el.querySelector('#backBtn');
  if (!backBtn) return;
  backBtn.addEventListener('click', () => {
    if (window.history.length > 1) {
      window.history.back();
    } else {
      ctx.navigate('#/');
    }
  });
}

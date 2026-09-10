import { latestRecords, fmtValue, fmtDelta, dateLabel, halfYearLabel, esc, SHORT_LABELS } from '../data.js';

// 홈의 첫 필만 목업대로 '취업자 증감'을 온전히 유지하고, 나머지는 공유 축약 라벨을 쓴다.
const PILLS = [
  { code: 'emp_change', label: '취업자 증감' },
  { code: 'unemp_rate', label: SHORT_LABELS.unemp_rate },
  { code: 'gdp_growth', label: SHORT_LABELS.gdp_growth },
  { code: 'cpi', label: SHORT_LABELS.cpi },
];

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
      <div class="num" style="font-size:15px;font-weight:700;white-space:nowrap;">${esc(String(year))}년 전망</div>
      <button type="button" id="yearNext" aria-label="다음 연도" style="display:flex;align-items:center;justify-content:center;width:44px;height:44px;background:none;border:none;color:#98a2b3;cursor:pointer;">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#98a2b3" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"></polyline></svg>
      </button>
    </div>`;
}

// ── 기관별 전망치 세로 막대 ────────────────────────────────────────────────
//
// 축 규칙이 지표마다 다르다. 하나로 통일하면 둘 중 하나가 반드시 망가진다.
//
// **취업자 증감(만명)은 0 이 뜻을 갖는다** — 0 아래면 고용이 줄어든다는 말이다.
// 그래서 0 을 기준선으로 살리고 막대를 그 위아래로 뻗는다. 이 축에서는 막대
// 길이를 값의 크기로 읽어도 된다.
//
// **비율 지표(실업률·성장률·물가)는 기관 간 폭이 아주 좁다.** 2026년 실업률은
// 여섯 기관이 2.8~2.9 안에 다 들어간다 — 0 을 바닥으로 잡으면 막대가 96.6%
// 대 100% 가 되어 눈으로는 똑같다. 그래서 최저~최고에 축을 맞춘다.
// **대신 이 축에서 막대 길이는 값의 절대 크기가 아니라 기관 간 상대 위치다.**
// 그 사실을 화면에도 한 줄로 적는다(orgbars__note) — 안 적으면 0.1%p 차이를
// 세 배 차이로 읽는다.
//
// 최저 기관을 바닥에 딱 붙이면 막대가 사라져 '자료 없음'처럼 보이므로,
// 최저 아래로 범위의 RANGE_PAD 만큼 여백을 둔다.
const ZERO_BASED = new Set(['emp_change']);
const RANGE_PAD = 0.35;

const VB_W = 330;
const TOP_PAD = 13;   // 막대 위 값 라벨 자리
const PLOT_H = 46;    // 막대가 쓰는 세로 — 납작하게 두되 높이 차이는 분별되는 선
const LABEL_H = 15;   // 막대 아래 기관명 자리
const VB_H = TOP_PAD + PLOT_H + LABEL_H;

// fractions 는 그림 안에서 막대가 차지할 비율이다.
// signed 축에서는 부호가 있다(0 기준 위/아래). 아닌 축에서는 늘 0~1.
export function barGeometry(indicator, values) {
  const max = Math.max(...values);
  const min = Math.min(...values);

  if (ZERO_BASED.has(indicator)) {
    const top = Math.max(max, 0);
    const bottom = Math.min(min, 0);
    const span = top - bottom || 1;
    return {
      signed: true,
      zeroAt: (0 - bottom) / span,
      fractions: values.map(v => v / span),
    };
  }

  const range = max - min;
  if (range === 0) {
    // 전 기관이 같은 값 — 없는 차이를 그리지 않는다. 나란히 반 높이로 둔다.
    return { signed: false, zeroAt: 0, fractions: values.map(() => 0.5) };
  }

  const bottom = min - range * RANGE_PAD;
  return {
    signed: false,
    zeroAt: 0,
    fractions: values.map(v => (v - bottom) / (max - bottom)),
  };
}

// 약칭은 화면이 지어내지 않고 orgs.json 이 갖는다(short_ko). 막대 아래 칸은
// 여섯 기관이면 55px 뿐이라 '한국고용정보원'이 그대로는 안 들어간다.
// 데이터에 약칭이 없으면 본 이름으로 떨어진다 — 짓느니 넘치는 편이 낫다.
function shortName(rec, orgs) {
  const meta = (orgs || []).find(o => o.org === rec.org);
  return (meta && meta.short_ko) || rec.org_name_ko;
}

function renderOrgBars(latest, orgs) {
  if (!latest.length) return '';

  // 카드 목록은 발표일 순이지만 그래프는 값 순이어야 높낮이가 한눈에 읽힌다.
  const rows = latest.slice().sort((a, b) => b.value - a.value);
  const geo = barGeometry(rows[0].indicator, rows.map(r => r.value));

  const plotBottom = TOP_PAD + PLOT_H;
  const zeroY = plotBottom - geo.zeroAt * PLOT_H;
  const slotW = VB_W / rows.length;
  const barW = Math.min(30, slotW * 0.46);

  const bars = rows.map((rec, i) => {
    const cx = slotW * (i + 0.5);
    const raw = geo.fractions[i] * PLOT_H;
    const negative = raw < 0;
    const h = Math.max(2, Math.abs(raw));
    const y = geo.signed ? (negative ? zeroY : zeroY - h) : plotBottom - h;
    const valueY = negative ? y + h + 10 : y - 4;
    const [valueText] = splitValueUnit(fmtValue(rec));

    return `
      <rect x="${(cx - barW / 2).toFixed(1)}" y="${y.toFixed(1)}" width="${barW.toFixed(1)}" height="${h.toFixed(1)}" rx="2" fill="${negative ? '#7f9dc4' : '#23508f'}"></rect>
      <text x="${cx.toFixed(1)}" y="${valueY.toFixed(1)}" font-size="10" font-weight="700" fill="#23508f" text-anchor="middle">${esc(valueText)}</text>
      <text x="${cx.toFixed(1)}" y="${VB_H - 3}" font-size="10" fill="#667085" text-anchor="middle">${esc(shortName(rec, orgs))}</text>`;
  }).join('');

  const zeroLine = geo.signed
    ? `<line x1="0" y1="${zeroY.toFixed(1)}" x2="${VB_W}" y2="${zeroY.toFixed(1)}" stroke="#c3cede" stroke-width="1"></line>`
    : '';

  return `
    <div class="orgbars">
      <svg width="100%" height="${VB_H}" viewBox="0 0 ${VB_W} ${VB_H}" fill="none" role="img" aria-label="기관별 전망치 막대그래프">
        ${zeroLine}
        ${bars}
      </svg>
      ${geo.signed ? '' : '<div class="orgbars__note">막대 높이는 기관 간 상대 위치</div>'}
    </div>`;
}

// ───────────────────────────────────────────────────────────────────────────

// 카드에 싣는 것은 넷뿐이다: 연전망 · 상하반기 전망 · 발표시점 · 보고서명.
// 근거 문장과 수집 상태(자동/검증/확인)는 일부러 뺐다 — 사용자 결정이다.
//
// **두 줄이다.** 넷을 넉 줄로 쌓으면 카드 하나가 104px 이라 한 화면에 두세
// 기관밖에 안 들어온다 — 이 화면의 일은 기관들을 나란히 놓고 보는 것이다.
//   1줄: 기관명 · 연간 전망치 · 증감 · 상하반기
//   2줄: 발표시기 · 보고서명
//
// 첫 줄은 좁은 폭에서 넘칠 수 있다(가장 긴 조합이 '한국고용정보원' + 14.6만명
// + ▼-1.6만명 + 상하반기다). 그래서 wrap 을 허용해 상하반기만 아래로
// 떨어지게 둔다 — nowrap 으로 눌러 두면 기관명이 잘리거나 가로 스크롤이 난다.
// 기관명·수치·증감은 각자 nowrap 이라 낱말 중간에서 쪼개지지는 않는다.
function renderCard(rec, ctx) {
  const delta = fmtDelta(rec);
  const deltaCls = delta.dir === 'up' ? 'delta-up' : delta.dir === 'down' ? 'delta-down' : 'delta-flat';
  const deltaSvg = DELTA_SVG[delta.dir] || '';
  const [value, unitSuffix] = splitValueUnit(fmtValue(rec));

  return `
    <button type="button" class="card" data-org="${esc(rec.org)}" style="display:flex;flex-direction:column;gap:2px;text-align:left;width:100%;cursor:pointer;padding:9px 12px;">
      <div style="display:flex;align-items:baseline;flex-wrap:wrap;gap:4px 6px;width:100%;">
        <div style="font-size:13px;font-weight:600;white-space:nowrap;">${esc(rec.org_name_ko)}</div>
        <div class="num" style="font-size:20px;font-weight:700;white-space:nowrap;">${esc(value)}<span style="font-size:12px;font-weight:600;">${esc(unitSuffix)}</span></div>
        <div class="delta ${deltaCls}" style="font-size:12px;white-space:nowrap;">${deltaSvg}<span class="num">${esc(delta.text)}</span></div>
        <div class="num" style="margin-left:auto;font-size:11px;color:#667085;white-space:nowrap;">${esc(halfYearLabel(ctx.records, rec, { compact: true }))}</div>
      </div>
      <div style="display:flex;gap:6px;font-size:11px;color:#98a2b3;width:100%;">
        <span class="num" style="flex:none;">${esc(dateLabel(rec, ctx.orgs))}</span>
        <span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${esc(rec.report_title)}</span>
      </div>
    </button>`;
}

function splitValueUnit(formatted) {
  const match = formatted.match(/^(-?[\d.]+)(.*)$/);
  if (!match) return [formatted, ''];
  return [match[1], match[2]];
}

function lastCollectedLabel(records) {
  const withDate = records.filter(r => r.collected_at);
  if (!withDate.length) return '';
  const max = withDate.reduce((a, b) => (b.collected_at > a.collected_at ? b : a));
  return max.collected_at.slice(0, 16).replace('T', ' ');
}

export function render(el, ctx) {
  const { records, state } = ctx;

  if (!PILLS.some(p => p.code === state.indicator)) {
    state.indicator = 'emp_change';
  }

  const availableYears = yearsForIndicator(records, state.indicator);
  if (availableYears.length && !availableYears.includes(state.year)) {
    state.year = availableYears[availableYears.length - 1];
  }

  const latest = latestRecords(records, { indicator: state.indicator, targetYear: state.year });

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
      </div>`;
  }

  el.innerHTML = `
    ${renderPills(ctx)}
    ${renderYearSwitch(state.year)}
    ${renderOrgBars(latest, ctx.orgs)}
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

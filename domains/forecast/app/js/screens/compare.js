import { compareSet, summarize, fmtValue, fmtNumber, dateLabel, esc, isOcrSourced } from '../data.js';

const OCR_BADGE_TITLE = 'PDF 이미지를 OCR로 읽은 수치입니다 — 원문과 대조해 확인하세요.';

const FILTERS = [
  { code: 'all', label: '전체' },
  { code: 'domestic', label: '국내' },
  { code: 'intl', label: '국제' },
];

// 클릭 직후 표시되는 일시적 라벨('복사됨')을 되돌릴 원본 텍스트.
// 클릭 핸들러 안에서 매번 copyLabel.textContent를 읽어 "원본"으로 삼으면,
// 1.5초 타이머가 끝나기 전에 다시 클릭했을 때 그 순간의 임시 라벨('복사됨')을
// 원본으로 착각해 이후 영구히 '복사됨'으로 고정되는 버그가 생긴다.
// 라벨 문구 자체는 바뀌지 않으므로 모듈 상수로 고정해 둔다.
const COPY_LABEL_DEFAULT = '표로 보기 (보고서용 복사)';

function yearsForIndicator(records, indicator) {
  const years = new Set(records.filter(r => r.indicator === indicator).map(r => r.target_year));
  return Array.from(years).sort((a, b) => a - b);
}

function splitValueUnit(formatted) {
  const match = formatted.match(/^(-?[\d.]+)(.*)$/);
  if (!match) return [formatted, ''];
  return [match[1], match[2]];
}

function renderSelectors(ctx, compareState, availableYears) {
  const indicatorOptions = ctx.indicators.map(ind =>
    `<option value="${esc(ind.code)}"${ind.code === compareState.indicator ? ' selected' : ''}>${esc(ind.name_ko)}</option>`
  ).join('');

  const yearOptions = availableYears.map(y =>
    `<option value="${esc(String(y))}"${y === compareState.year ? ' selected' : ''}>${esc(String(y))}</option>`
  ).join('');

  const selectStyle = 'font-family:inherit;font-size:13px;font-weight:600;color:var(--text);background:var(--card);border:1px solid var(--border);padding:6px 28px 6px 12px;border-radius:8px;min-height:44px;';

  return `
    <div style="display:flex;align-items:center;gap:8px;">
      <select id="indicatorSelect" class="num" style="${selectStyle}">${indicatorOptions}</select>
      <select id="yearSelect" class="num" style="${selectStyle}"${availableYears.length ? '' : ' disabled'}>${yearOptions}</select>
      <div style="margin-left:auto;display:flex;gap:6px;">
        ${FILTERS.map(f => `<button type="button" class="pill${compareState.filter === f.code ? ' pill--active' : ''}" data-filter="${esc(f.code)}" style="min-height:44px;">${esc(f.label)}</button>`).join('')}
      </div>
    </div>`;
}

function renderBars(set, orgsMeta) {
  if (!set.length) {
    return `
      <div style="flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:6px;padding:32px 16px;text-align:center;">
        <div style="font-size:14px;font-weight:600;color:var(--text-secondary);">아직 수집된 전망이 없습니다</div>
      </div>`;
  }

  const values = set.map(e => e.rec.value);
  const maxValue = Math.max(...values);

  const rows = set.map(({ rec, stale, monthLabel }) => {
    const widthPct = maxValue <= 0 ? 50 : Math.max(4, Math.min(100, (rec.value / maxValue) * 100));
    const barColor = stale ? '#7f9dc4' : '#23508f';
    const [valueText] = splitValueUnit(fmtValue(rec));
    const ocrBadge = isOcrSourced(rec, orgsMeta)
      ? `<div class="badge badge--ocr" style="flex-shrink:0;" title="${esc(OCR_BADGE_TITLE)}">확인필요</div>`
      : '';

    return `
      <button type="button" class="num" data-org="${esc(rec.org)}" style="display:flex;align-items:center;gap:10px;width:100%;background:none;border:none;padding:2px 0;text-align:left;cursor:pointer;min-height:44px;${stale ? 'opacity:.45;' : ''}">
        <div style="width:62px;flex-shrink:0;font-size:13px;font-weight:600;color:var(--text);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${esc(rec.org_name_ko)}</div>
        <div style="flex:1;height:18px;background:var(--bg);border-radius:4px;overflow:hidden;">
          <div style="width:${widthPct.toFixed(1)}%;height:18px;background:${barColor};border-radius:4px;"></div>
        </div>
        ${ocrBadge}
        <div style="min-width:30px;font-size:14px;font-weight:700;text-align:right;color:var(--text);">${esc(valueText)}</div>
        <div style="min-width:38px;font-size:11px;color:var(--text-muted);text-align:right;">${esc(monthLabel)}</div>
      </button>`;
  }).join('');

  return `
    <div class="card" style="margin:12px 16px 0 16px;padding:14px;display:flex;flex-direction:column;gap:10px;">
      ${rows}
    </div>`;
}

function renderBand(set, indicatorMeta) {
  if (!set.length) return '';
  const recs = set.map(e => e.rec);
  const summary = summarize(recs);
  const countText = `${summary.count}개 기관`;

  if (summary.count < 2) {
    return `
      <div style="margin:10px 16px 0 16px;padding:10px 14px;background:var(--accent-light);border-radius:10px;display:flex;align-items:center;justify-content:flex-end;">
        <div class="num" style="font-size:12px;color:var(--text-secondary);">${esc(countText)}</div>
      </div>`;
  }

  const unit = indicatorMeta ? indicatorMeta.unit : '';
  const gapUnit = unit === '만명' ? '만명' : '%p';
  const gapText = fmtNumber(summary.max.value - summary.min.value, unit);
  const avgText = fmtNumber(summary.avg, unit);

  return `
    <div style="margin:10px 16px 0 16px;padding:10px 14px;background:var(--accent-light);border-radius:10px;display:flex;align-items:center;justify-content:space-between;gap:8px;">
      <div class="num" style="font-size:13px;font-weight:600;color:var(--accent);">격차 ${esc(gapText)}${esc(gapUnit)} · 평균 ${esc(avgText)}${esc(unit)}</div>
      <div class="num" style="font-size:12px;color:var(--text-secondary);">${esc(countText)}</div>
    </div>`;
}

function renderWarning() {
  return `
    <div style="margin:8px 16px 0 16px;padding:10px 14px;background:var(--badge-extracted-bg);border-radius:10px;display:flex;gap:8px;align-items:flex-start;">
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#9a6b15" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink:0;margin-top:1px;"><path d="M12 3 2 20h20L12 3z"></path><line x1="12" y1="10" x2="12" y2="14"></line><circle cx="12" cy="17" r="0.5" fill="#9a6b15"></circle></svg>
      <div style="font-size:12px;line-height:1.5;color:var(--badge-extracted-fg);">발표 시점이 상이하므로 단순 비교에 유의하세요. 3개월 이상 지난 전망은 흐리게 표시됩니다.</div>
    </div>`;
}

function renderCopyButton() {
  return `
    <button type="button" id="copyBtn" style="margin:10px 16px 0 16px;display:flex;align-items:center;justify-content:center;gap:8px;padding:12px;background:var(--card);border:1px solid #cfd6df;border-radius:10px;font-size:14px;font-weight:600;color:var(--accent);min-height:44px;cursor:pointer;">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="16" rx="1"></rect><line x1="3" y1="9" x2="21" y2="9"></line><line x1="3" y1="14" x2="21" y2="14"></line><line x1="12" y1="4" x2="12" y2="20"></line></svg>
      <span id="copyLabel">${esc(COPY_LABEL_DEFAULT)}</span>
    </button>
    <div id="copyFallback" style="display:none;margin:8px 16px 0 16px;">
      <textarea id="copyTextarea" readonly style="width:100%;min-height:100px;font-size:12px;font-family:inherit;padding:8px;border:1px solid var(--border);border-radius:8px;background:var(--card);color:var(--text);box-sizing:border-box;"></textarea>
    </div>`;
}

function buildTableText(set, orgs) {
  const header = '기관\t값\t발표일';
  const rows = set.map(({ rec }) => `${rec.org_name_ko}\t${fmtValue(rec)}\t${dateLabel(rec, orgs)}`);
  return [header, ...rows].join('\n');
}

export function render(el, ctx) {
  const { records, orgs, indicatorMeta, state, today } = ctx;
  const compareState = state.compare;

  const availableYears = yearsForIndicator(records, compareState.indicator);
  if (availableYears.length && !availableYears.includes(compareState.year)) {
    compareState.year = availableYears[availableYears.length - 1];
  }

  const set = compareSet(records, {
    indicator: compareState.indicator,
    targetYear: compareState.year,
    today,
    orgsMeta: orgs,
    filter: compareState.filter,
  });

  const curMeta = indicatorMeta ? indicatorMeta[compareState.indicator] : null;
  const title = `${compareState.year}년 ${curMeta ? curMeta.name_ko : compareState.indicator} 비교`;

  el.innerHTML = `
    <div style="display:flex;flex-direction:column;gap:10px;padding:14px 16px 0 16px;">
      <div style="font-size:18px;font-weight:700;" class="num">${esc(title)}</div>
      ${renderSelectors(ctx, compareState, availableYears)}
    </div>
    ${renderBars(set, orgs)}
    ${renderBand(set, curMeta)}
    ${renderWarning()}
    ${renderCopyButton()}
  `;

  const indicatorSelect = el.querySelector('#indicatorSelect');
  if (indicatorSelect) {
    indicatorSelect.addEventListener('change', () => {
      compareState.indicator = indicatorSelect.value;
      ctx.rerender();
    });
  }

  const yearSelect = el.querySelector('#yearSelect');
  if (yearSelect) {
    yearSelect.addEventListener('change', () => {
      compareState.year = Number(yearSelect.value);
      ctx.rerender();
    });
  }

  el.querySelectorAll('[data-filter]').forEach(btn => {
    btn.addEventListener('click', () => {
      compareState.filter = btn.dataset.filter;
      ctx.rerender();
    });
  });

  el.querySelectorAll('[data-org]').forEach(row => {
    row.addEventListener('click', () => {
      ctx.navigate('#/org/' + encodeURIComponent(row.dataset.org));
    });
  });

  const copyBtn = el.querySelector('#copyBtn');
  const copyLabel = el.querySelector('#copyLabel');
  const copyFallback = el.querySelector('#copyFallback');
  const copyTextarea = el.querySelector('#copyTextarea');
  let copyRestoreTimer = null;
  if (copyBtn) {
    copyBtn.addEventListener('click', async () => {
      const text = buildTableText(set, orgs);
      try {
        if (!navigator.clipboard || !navigator.clipboard.writeText) throw new Error('clipboard unavailable');
        await navigator.clipboard.writeText(text);
        if (copyFallback) copyFallback.style.display = 'none';
        if (copyLabel) {
          copyLabel.textContent = '복사됨';
          // 연속 클릭 시 먼저 걸린 타이머가 나중에 발화해 라벨을 되돌리는 걸 막는다.
          clearTimeout(copyRestoreTimer);
          copyRestoreTimer = setTimeout(() => { copyLabel.textContent = COPY_LABEL_DEFAULT; }, 1500);
        }
      } catch {
        if (copyTextarea) copyTextarea.value = text;
        if (copyFallback) copyFallback.style.display = 'block';
      }
    });
  }
}
